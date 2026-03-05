package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/yourname/agent-02/src/security"
)

type DiscordAdapter struct {
	botToken      string
	applicationID string
	publicKey     string
	httpClient    *http.Client
}

type discordInteraction struct {
	Type      int    `json:"type"`
	ChannelID string `json:"channel_id"`
	Data      struct {
		Name    string `json:"name"`
		Options []struct {
			Name  string `json:"name"`
			Value any    `json:"value"`
		} `json:"options"`
	} `json:"data"`
	Member *struct {
		User struct {
			ID string `json:"id"`
		} `json:"user"`
	} `json:"member,omitempty"`
	User *struct {
		ID string `json:"id"`
	} `json:"user,omitempty"`
}

func NewDiscordAdapter(botToken, applicationID, publicKey string) *DiscordAdapter {
	return &DiscordAdapter{
		botToken:      botToken,
		applicationID: applicationID,
		publicKey:     publicKey,
		httpClient: &http.Client{
			Timeout: 20 * time.Second,
		},
	}
}

func (a *DiscordAdapter) Enabled() bool {
	return a.botToken != "" && a.publicKey != ""
}

func (a *DiscordAdapter) SelfTest(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "https://discord.com/api/v10/applications/@me", nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bot "+a.botToken)
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("discord self test failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *DiscordAdapter) ParseInteraction(c *fiber.Ctx) (InboundMessage, int, error) {
	body := c.Body()
	signature := c.Get("X-Signature-Ed25519")
	timestamp := c.Get("X-Signature-Timestamp")
	if err := security.VerifyDiscordSignature(a.publicKey, signature, timestamp, body); err != nil {
		return InboundMessage{}, 0, fiber.ErrUnauthorized
	}

	var payload discordInteraction
	if err := json.Unmarshal(body, &payload); err != nil {
		return InboundMessage{}, 0, err
	}
	if payload.Type == 1 {
		return InboundMessage{}, 1, nil
	}
	if payload.Type != 2 {
		return InboundMessage{}, payload.Type, fiber.NewError(fiber.StatusNoContent, "no content")
	}

	prompt := ""
	for _, opt := range payload.Data.Options {
		if opt.Name == "prompt" {
			if s, ok := opt.Value.(string); ok {
				prompt = s
			}
		}
	}
	if strings.TrimSpace(prompt) == "" {
		prompt = "hello"
	}

	userID := ""
	if payload.Member != nil {
		userID = payload.Member.User.ID
	} else if payload.User != nil {
		userID = payload.User.ID
	}

	return InboundMessage{
		Platform:  "discord",
		ChannelID: payload.ChannelID,
		UserID:    userID,
		Text:      prompt,
	}, payload.Type, nil
}

func (a *DiscordAdapter) InteractionPong(c *fiber.Ctx) error {
	return c.JSON(map[string]any{"type": 1})
}

func (a *DiscordAdapter) InteractionMessage(c *fiber.Ctx, content string) error {
	return c.JSON(map[string]any{
		"type": 4,
		"data": map[string]any{
			"content": content,
		},
	})
}

func (a *DiscordAdapter) SendText(ctx context.Context, channelID string, text string) error {
	payload := map[string]any{"content": text}
	buf := &bytes.Buffer{}
	_ = json.NewEncoder(buf).Encode(payload)
	url := fmt.Sprintf("https://discord.com/api/v10/channels/%s/messages", channelID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, buf)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bot "+a.botToken)
	req.Header.Set("Content-Type", "application/json")
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("discord send failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}
