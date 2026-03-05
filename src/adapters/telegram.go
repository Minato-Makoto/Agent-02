package adapters

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

type TelegramAdapter struct {
	botToken      string
	webhookSecret string
	webhookPath   string
	baseURL       string
	httpClient    *http.Client
}

type telegramUpdate struct {
	Message *struct {
		Text string `json:"text"`
		From struct {
			ID int64 `json:"id"`
		} `json:"from"`
		Chat struct {
			ID int64 `json:"id"`
		} `json:"chat"`
	} `json:"message"`
}

func NewTelegramAdapter(botToken, webhookSecret, webhookPath string) *TelegramAdapter {
	if webhookPath == "" {
		webhookPath = "/webhooks/telegram"
	}
	return &TelegramAdapter{
		botToken:      botToken,
		webhookSecret: webhookSecret,
		webhookPath:   webhookPath,
		baseURL:       "https://api.telegram.org",
		httpClient: &http.Client{
			Timeout: 20 * time.Second,
		},
	}
}

func (a *TelegramAdapter) Enabled() bool {
	return a.botToken != ""
}

func (a *TelegramAdapter) ConfigureWebhook(ctx context.Context, publicURL string) error {
	if publicURL == "" || !a.Enabled() {
		return nil
	}
	payload := map[string]any{
		"url": publicURL + a.webhookPath,
	}
	if a.webhookSecret != "" {
		payload["secret_token"] = a.webhookSecret
	}
	buf := &bytes.Buffer{}
	_ = json.NewEncoder(buf).Encode(payload)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.endpoint("setWebhook"), buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("setWebhook failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *TelegramAdapter) SelfTest(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, a.endpoint("getMe"), nil)
	if err != nil {
		return err
	}
	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("telegram getMe failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *TelegramAdapter) ParseWebhook(c *fiber.Ctx) (InboundMessage, error) {
	if a.webhookSecret != "" {
		sig := c.Get("X-Telegram-Bot-Api-Secret-Token")
		if sig != a.webhookSecret {
			return InboundMessage{}, fiber.ErrUnauthorized
		}
	}

	var update telegramUpdate
	if err := c.BodyParser(&update); err != nil {
		return InboundMessage{}, err
	}
	if update.Message == nil || strings.TrimSpace(update.Message.Text) == "" {
		return InboundMessage{}, fiber.ErrNoContent
	}

	return InboundMessage{
		Platform:  "telegram",
		ChannelID: strconv.FormatInt(update.Message.Chat.ID, 10),
		UserID:    strconv.FormatInt(update.Message.From.ID, 10),
		Text:      update.Message.Text,
	}, nil
}

func (a *TelegramAdapter) SendText(ctx context.Context, channelID string, text string) error {
	chatID, err := strconv.ParseInt(channelID, 10, 64)
	if err != nil {
		return err
	}
	payload := map[string]any{
		"chat_id": chatID,
		"text":    text,
	}
	buf := &bytes.Buffer{}
	_ = json.NewEncoder(buf).Encode(payload)

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, a.endpoint("sendMessage"), buf)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
		return fmt.Errorf("telegram sendMessage failed: %s %s", resp.Status, strings.TrimSpace(string(body)))
	}
	return nil
}

func (a *TelegramAdapter) endpoint(method string) string {
	return fmt.Sprintf("%s/bot%s/%s", a.baseURL, a.botToken, method)
}