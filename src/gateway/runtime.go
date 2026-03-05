package gateway

import (
	"github.com/yourname/agent-02/src/adapters"
	"github.com/yourname/agent-02/src/config"
	"github.com/yourname/agent-02/src/store"
)

type Runtime struct {
	Config    config.AppConfig
	DataDir   string
	DB        *store.SQLiteStore
	Service   *Service
	Telegram  *adapters.TelegramAdapter
	WhatsApp  *adapters.WhatsAppCloudAdapter
	Discord   *adapters.DiscordAdapter
}