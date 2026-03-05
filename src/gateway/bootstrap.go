package gateway

import (
	"context"
	"fmt"
	"strings"

	"github.com/google/uuid"
	"github.com/yourname/agent-02/src/adapters"
	"github.com/yourname/agent-02/src/llm"
	"github.com/yourname/agent-02/src/security"
	"github.com/yourname/agent-02/src/skills"
	"github.com/yourname/agent-02/src/store"
)

func BuildRuntime(ctx context.Context, dataDir string) (*Runtime, []byte, error) {
	cfg, err := store.LoadConfig(dataDir)
	if err != nil {
		return nil, nil, err
	}

	masterKey, err := security.LoadOrCreateMasterKey(dataDir)
	if err != nil {
		return nil, nil, err
	}

	if strings.TrimSpace(cfg.Security.AdminTokenEnc) == "" {
		tokenPlain := uuid.NewString()
		tokenEnc, err := security.EncryptString(masterKey, tokenPlain)
		if err != nil {
			return nil, nil, err
		}
		cfg.Security.AdminTokenEnc = tokenEnc
		if err := store.SaveConfig(dataDir, cfg); err != nil {
			return nil, nil, err
		}
		fmt.Printf("[agent02] generated admin token once: %s\n", tokenPlain)
	}

	db, err := store.OpenSQLite(dataDir)
	if err != nil {
		return nil, nil, err
	}

	runner := skills.NewRunner(db)
	runner.Register(skills.NewNotesTool(db))
	llmManager := llm.NewManager(cfg.LLM, masterKey)

	runtime := &Runtime{
		Config:  cfg,
		DataDir: dataDir,
		DB:      db,
		Service: NewService(llmManager, runner, db, cfg.Skills.Enabled),
	}

	if cfg.Connectors.Telegram.Enabled {
		token, _ := security.DecryptString(masterKey, cfg.Connectors.Telegram.BotTokenEnc)
		secret, _ := security.DecryptString(masterKey, cfg.Connectors.Telegram.WebhookSecretEnc)
		if strings.TrimSpace(token) != "" {
			runtime.Telegram = adapters.NewTelegramAdapter(token, secret, cfg.Connectors.Telegram.WebhookPath)
			_ = runtime.Telegram.ConfigureWebhook(ctx, cfg.Server.PublicURL)
		}
	}

	if cfg.Connectors.WhatsApp.Enabled {
		phoneID, _ := security.DecryptString(masterKey, cfg.Connectors.WhatsApp.PhoneNumberIDEnc)
		accessToken, _ := security.DecryptString(masterKey, cfg.Connectors.WhatsApp.AccessTokenEnc)
		appSecret, _ := security.DecryptString(masterKey, cfg.Connectors.WhatsApp.AppSecretEnc)
		verifyToken, _ := security.DecryptString(masterKey, cfg.Connectors.WhatsApp.VerifyTokenEnc)
		if strings.TrimSpace(phoneID) != "" && strings.TrimSpace(accessToken) != "" {
			runtime.WhatsApp = adapters.NewWhatsAppCloudAdapter(
				phoneID,
				accessToken,
				appSecret,
				verifyToken,
				cfg.Connectors.WhatsApp.GraphAPIVersion,
			)
		}
	}

	if cfg.Connectors.Discord.Enabled {
		botToken, _ := security.DecryptString(masterKey, cfg.Connectors.Discord.BotTokenEnc)
		appID, _ := security.DecryptString(masterKey, cfg.Connectors.Discord.ApplicationIDEnc)
		publicKey, _ := security.DecryptString(masterKey, cfg.Connectors.Discord.PublicKeyEnc)
		if strings.TrimSpace(botToken) != "" && strings.TrimSpace(publicKey) != "" {
			runtime.Discord = adapters.NewDiscordAdapter(botToken, appID, publicKey)
		}
	}

	return runtime, masterKey, nil
}