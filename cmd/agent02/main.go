package main

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/spf13/cobra"
	"github.com/yourname/agent-02/src/api"
	"github.com/yourname/agent-02/src/config"
	"github.com/yourname/agent-02/src/gateway"
	"github.com/yourname/agent-02/src/security"
	"github.com/yourname/agent-02/src/store"
)

func main() {
	var dataDir string

	root := &cobra.Command{
		Use:   "agent02",
		Short: "Agent-02 secure self-hosted AI gateway",
	}
	root.PersistentFlags().StringVar(&dataDir, "data-dir", "data", "Path to data directory")

	root.AddCommand(startCommand(&dataDir))
	root.AddCommand(connectCommand(&dataDir))
	root.AddCommand(skillsCommand(&dataDir))

	if err := root.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func startCommand(dataDir *string) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "start",
		Short: "Start Agent-02 gateway service",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
			defer stop()

			runtimeState, masterKey, err := gateway.BuildRuntime(ctx, filepath.Clean(*dataDir))
			if err != nil {
				return err
			}
			defer runtimeState.DB.Close()

			server, err := api.NewServer(runtimeState, masterKey)
			if err != nil {
				return err
			}

			url := fmt.Sprintf("http://%s:%d", runtimeState.Config.Server.Host, runtimeState.Config.Server.Port)
			fmt.Printf("Agent-02 running at %s\n", url)
			fmt.Println("Connectors: official Telegram / WhatsApp Cloud / Discord")
			go func() {
				time.Sleep(500 * time.Millisecond)
				_ = openBrowser(url)
			}()
			return server.Listen(ctx)
		},
	}
	return cmd
}

func connectCommand(dataDir *string) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "connect",
		Short: "Configure official connector credentials",
	}

	cmd.AddCommand(connectTelegramCommand(dataDir))
	cmd.AddCommand(connectWhatsAppCommand(dataDir))
	cmd.AddCommand(connectDiscordCommand(dataDir))
	return cmd
}

func connectTelegramCommand(dataDir *string) *cobra.Command {
	var token string
	var secret string
	var enabled bool
	cmd := &cobra.Command{
		Use:   "telegram",
		Short: "Configure Telegram Bot API connector",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, key, err := loadConfigAndKey(*dataDir)
			if err != nil {
				return err
			}
			cfg.Connectors.Telegram.Enabled = enabled
			if token != "" {
				enc, err := security.EncryptString(key, token)
				if err != nil {
					return err
				}
				cfg.Connectors.Telegram.BotTokenEnc = enc
			}
			if secret != "" {
				enc, err := security.EncryptString(key, secret)
				if err != nil {
					return err
				}
				cfg.Connectors.Telegram.WebhookSecretEnc = enc
			}
			return store.SaveConfig(*dataDir, cfg)
		},
	}
	cmd.Flags().StringVar(&token, "token", "", "Telegram Bot API token")
	cmd.Flags().StringVar(&secret, "webhook-secret", "", "Webhook secret token")
	cmd.Flags().BoolVar(&enabled, "enable", true, "Enable connector")
	return cmd
}

func connectWhatsAppCommand(dataDir *string) *cobra.Command {
	var phoneID string
	var accessToken string
	var appSecret string
	var verifyToken string
	var enabled bool
	cmd := &cobra.Command{
		Use:   "whatsapp",
		Short: "Configure WhatsApp Business Cloud API connector",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, key, err := loadConfigAndKey(*dataDir)
			if err != nil {
				return err
			}
			cfg.Connectors.WhatsApp.Enabled = enabled
			if phoneID != "" {
				enc, err := security.EncryptString(key, phoneID)
				if err != nil {
					return err
				}
				cfg.Connectors.WhatsApp.PhoneNumberIDEnc = enc
			}
			if accessToken != "" {
				enc, err := security.EncryptString(key, accessToken)
				if err != nil {
					return err
				}
				cfg.Connectors.WhatsApp.AccessTokenEnc = enc
			}
			if appSecret != "" {
				enc, err := security.EncryptString(key, appSecret)
				if err != nil {
					return err
				}
				cfg.Connectors.WhatsApp.AppSecretEnc = enc
			}
			if verifyToken != "" {
				enc, err := security.EncryptString(key, verifyToken)
				if err != nil {
					return err
				}
				cfg.Connectors.WhatsApp.VerifyTokenEnc = enc
			}
			return store.SaveConfig(*dataDir, cfg)
		},
	}
	cmd.Flags().StringVar(&phoneID, "phone-number-id", "", "WhatsApp Cloud API phone number id")
	cmd.Flags().StringVar(&accessToken, "access-token", "", "WhatsApp Cloud API access token")
	cmd.Flags().StringVar(&appSecret, "app-secret", "", "Meta app secret for webhook signature validation")
	cmd.Flags().StringVar(&verifyToken, "verify-token", "", "Webhook verify token")
	cmd.Flags().BoolVar(&enabled, "enable", true, "Enable connector")
	return cmd
}

func connectDiscordCommand(dataDir *string) *cobra.Command {
	var token string
	var appID string
	var publicKey string
	var enabled bool
	cmd := &cobra.Command{
		Use:   "discord",
		Short: "Configure Discord official bot connector",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, key, err := loadConfigAndKey(*dataDir)
			if err != nil {
				return err
			}
			cfg.Connectors.Discord.Enabled = enabled
			if token != "" {
				enc, err := security.EncryptString(key, token)
				if err != nil {
					return err
				}
				cfg.Connectors.Discord.BotTokenEnc = enc
			}
			if appID != "" {
				enc, err := security.EncryptString(key, appID)
				if err != nil {
					return err
				}
				cfg.Connectors.Discord.ApplicationIDEnc = enc
			}
			if publicKey != "" {
				enc, err := security.EncryptString(key, publicKey)
				if err != nil {
					return err
				}
				cfg.Connectors.Discord.PublicKeyEnc = enc
			}
			return store.SaveConfig(*dataDir, cfg)
		},
	}
	cmd.Flags().StringVar(&token, "token", "", "Discord bot token")
	cmd.Flags().StringVar(&appID, "application-id", "", "Discord application id")
	cmd.Flags().StringVar(&publicKey, "public-key", "", "Discord interactions public key")
	cmd.Flags().BoolVar(&enabled, "enable", true, "Enable connector")
	return cmd
}

func skillsCommand(dataDir *string) *cobra.Command {
	root := &cobra.Command{
		Use:   "skills",
		Short: "Manage secure skills",
	}

	var skillName string
	var enable bool
	cmd := &cobra.Command{
		Use:   "enable",
		Short: "Enable or disable one skill",
		RunE: func(cmd *cobra.Command, args []string) error {
			cfg, _, err := loadConfigAndKey(*dataDir)
			if err != nil {
				return err
			}
			skillName = strings.ToLower(strings.TrimSpace(skillName))
			if skillName == "" {
				return fmt.Errorf("--skill is required")
			}
			if cfg.Skills.Enabled == nil {
				cfg.Skills.Enabled = map[string]bool{}
			}
			cfg.Skills.Enabled[skillName] = enable
			return store.SaveConfig(*dataDir, cfg)
		},
	}
	cmd.Flags().StringVar(&skillName, "skill", "", "Skill name, e.g. notes")
	cmd.Flags().BoolVar(&enable, "on", true, "Enable if true; disable if false")
	root.AddCommand(cmd)
	return root
}

func loadConfigAndKey(dataDir string) (config.AppConfig, []byte, error) {
	cleanDir := filepath.Clean(dataDir)
	cfg, err := store.LoadConfig(cleanDir)
	if err != nil {
		return config.AppConfig{}, nil, err
	}
	key, err := security.LoadOrCreateMasterKey(cleanDir)
	if err != nil {
		return config.AppConfig{}, nil, err
	}
	return cfg, key, nil
}

func openBrowser(url string) error {
	var cmd *exec.Cmd
	switch runtime.GOOS {
	case "windows":
		cmd = exec.Command("rundll32", "url.dll,FileProtocolHandler", url)
	case "darwin":
		cmd = exec.Command("open", url)
	default:
		cmd = exec.Command("xdg-open", url)
	}
	return cmd.Start()
}