package config

import "path/filepath"

type AppConfig struct {
	Server     ServerConfig     `json:"server"`
	Security   SecurityConfig   `json:"security"`
	Connectors ConnectorsConfig `json:"connectors"`
	LLM        LLMConfig        `json:"llm"`
	Skills     SkillsConfig     `json:"skills"`
}

type ServerConfig struct {
	Host             string `json:"host"`
	Port             int    `json:"port"`
	PublicURL        string `json:"public_url"`
	ReadTimeoutSec   int    `json:"read_timeout_sec"`
	WriteTimeoutSec  int    `json:"write_timeout_sec"`
	IdleTimeoutSec   int    `json:"idle_timeout_sec"`
	RequestBodyLimit int    `json:"request_body_limit"`
}

type SecurityConfig struct {
	RequireAdminAuth bool   `json:"require_admin_auth"`
	AdminTokenEnc    string `json:"admin_token_enc"`
}

type ConnectorsConfig struct {
	Telegram TelegramConfig `json:"telegram"`
	WhatsApp WhatsAppConfig `json:"whatsapp"`
	Discord  DiscordConfig  `json:"discord"`
}

type TelegramConfig struct {
	Enabled          bool   `json:"enabled"`
	BotTokenEnc      string `json:"bot_token_enc"`
	WebhookSecretEnc string `json:"webhook_secret_enc"`
	WebhookPath      string `json:"webhook_path"`
}

type WhatsAppConfig struct {
	Enabled           bool   `json:"enabled"`
	PhoneNumberIDEnc  string `json:"phone_number_id_enc"`
	AccessTokenEnc    string `json:"access_token_enc"`
	AppSecretEnc      string `json:"app_secret_enc"`
	VerifyTokenEnc    string `json:"verify_token_enc"`
	GraphAPIVersion   string `json:"graph_api_version"`
	WebhookPath       string `json:"webhook_path"`
}

type DiscordConfig struct {
	Enabled          bool   `json:"enabled"`
	BotTokenEnc      string `json:"bot_token_enc"`
	ApplicationIDEnc string `json:"application_id_enc"`
	PublicKeyEnc     string `json:"public_key_enc"`
	WebhookPath      string `json:"webhook_path"`
}

type LLMConfig struct {
	Provider          string               `json:"provider"`
	Model             string               `json:"model"`
	SystemPrompt      string               `json:"system_prompt"`
	RequestTimeoutSec int                  `json:"request_timeout_sec"`
	MaxTokens         int                  `json:"max_tokens"`
	Temperature       float64              `json:"temperature"`
	Cloud             OpenAICompatConfig   `json:"cloud"`
	LocalLlamaCPP     OpenAICompatConfig   `json:"local_llamacpp"`
}

type OpenAICompatConfig struct {
	BaseURL   string `json:"base_url"`
	APIKeyEnc string `json:"api_key_enc"`
}

type SkillsConfig struct {
	Enabled      map[string]bool `json:"enabled"`
	AllowedRoots []string        `json:"allowed_roots"`
}

func DefaultConfig(dataDir string) AppConfig {
	return AppConfig{
		Server: ServerConfig{
			Host:             "127.0.0.1",
			Port:             8080,
			PublicURL:        "",
			ReadTimeoutSec:   10,
			WriteTimeoutSec:  30,
			IdleTimeoutSec:   60,
			RequestBodyLimit: 1 * 1024 * 1024,
		},
		Security: SecurityConfig{
			RequireAdminAuth: true,
			AdminTokenEnc:    "",
		},
		Connectors: ConnectorsConfig{
			Telegram: TelegramConfig{
				Enabled:     false,
				WebhookPath: "/webhooks/telegram",
			},
			WhatsApp: WhatsAppConfig{
				Enabled:         false,
				GraphAPIVersion: "v23.0",
				WebhookPath:     "/webhooks/whatsapp",
			},
			Discord: DiscordConfig{
				Enabled:     false,
				WebhookPath: "/webhooks/discord",
			},
		},
		LLM: LLMConfig{
			Provider:          "openai",
			Model:             "gpt-5",
			SystemPrompt:      "You are Agent-02. Keep responses concise, safe, and practical.",
			RequestTimeoutSec: 45,
			MaxTokens:         800,
			Temperature:       0.2,
			Cloud: OpenAICompatConfig{
				BaseURL: "https://api.openai.com",
			},
			LocalLlamaCPP: OpenAICompatConfig{
				BaseURL: "http://127.0.0.1:8081",
			},
		},
		Skills: SkillsConfig{
			Enabled: map[string]bool{
				"notes": true,
			},
			AllowedRoots: []string{filepath.Clean(dataDir)},
		},
	}
}