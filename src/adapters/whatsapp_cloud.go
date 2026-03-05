package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/yourname/agent-02/src/security"
)

type WhatsAppCloudAdapter struct {
	phoneNumberID string
	accessToken   string
	appSecret     string
	verifyToken   string
	apiVersion    string
	httpClient    *http.Client
}

type waWebhookPayload struct {
	Entry []struct {
		Changes []struct {
			Value struct {
				Messages []struct {
					From string `json:"from"`
					Text struct {
						Body string `json:"body"`
					} `json:"text"`
				} `json:"messages"`
			} `json:"value"`
		} `json:"changes"`
	} `json:"entry"`
}

func NewWhatsAppCloudAdapter(phoneNumberID, accessToken, appSecret, verifyToken, apiVersion string) *WhatsAppCloudAdapter {
	if apiVersion == "" {
		apiVersion = "v23.0"
	}
	return &WhatsAppCloudAdapter{
		phoneNumberID: phoneNumberID,
		accessToken:   accessToken,
		appSecret:     appSecret,
		verifyToken:   verifyToken,
		apiVersion:    apiVersion,
		httpClient: &http.Client{
			Timeout: 20 * time.Second,
		},
	}
}

func (a *WhatsAppCloudAdapter) Enabled() bool {
	return a.phoneNumberID != "" && a.accessToken != ""
}

func (a *WhatsAppCloudAdapter) VerifyWebhook(c *fiber.Ctx) error {
	mode := c.Query("hub.mode")
	token := c.Query("hub.verify_token")
	challenge := c.Query("hub.challenge")
	if mode == "subscribe" && token == a.verifyToken {
		return c.SendString(challenge)
	}
	return fiber.ErrUnauthorized
}

func (a *WhatsAppCloudAdapter) ParseWebhook(c *fiber.Ctx) (InboundMessage, error) {
	if !security.VerifyMetaSignature(c.Body(), a.appSecret, c.Get("X-Hub-Signature-256")) {
		return InboundMessage{}, fiber.ErrUnauthorized
	}

	var payload waWebhookPayload
	if err := c.BodyParser(&payload); err != nil {
		return InboundMessage{}, err
	}

	for _, entry := range payload.Entry {
		for _, change := range entry.Changes {
			for _, msg := range change.Value.Messages {
				if strings.TrimSpace(msg.Text.Body) == "" {
					continue
				}
				return InboundMessage{
					Platform:  "whatsapp",
					ChannelID: msg.From,
					UserID:    msg.From,
					Text:      msg.Text.Body,
				}, nil
			}
		}
	}

	return InboundMessage{}, fiber.ErrNoContent
}

func (a *WhatsAppCloudAdapter) SendText(ctx context.Context, channelID string, text string) error {
	payload := map[string]any{
		"messaging_product": "whatsapp",
		"recipient_type":    "individual",
		"to":                channelID,
		"type":              "text",
		"text": map[string]any{
			"body": text,
		},
	}
	buf := &bytes.Buffer{}
	_ = json.NewEncoder(buf).Encode(payload)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.messagesEndpoint(), buf)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+a.accessToken)
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("whatsapp send failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *WhatsAppCloudAdapter) SelfTest(ctx context.Context) error {
	u := fmt.Sprintf("https://graph.facebook.com/%s/%s?fields=display_phone_number", a.apiVersion, url.PathEscape(a.phoneNumberID))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+a.accessToken)
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("whatsapp self test failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *WhatsAppCloudAdapter) messagesEndpoint() string {
	return fmt.Sprintf("https://graph.facebook.com/%s/%s/messages", a.apiVersion, url.PathEscape(a.phoneNumberID))
}