package skills

import (
	"context"

	"github.com/yourname/agent-02/src/store"
)

type Request struct {
	Tool      string         `json:"tool"`
	Action    string         `json:"action"`
	Input     map[string]any `json:"input"`
	Actor     string         `json:"actor"`
	Platform  string         `json:"platform"`
	ChannelID string         `json:"channel_id"`
}

type Result struct {
	PendingConsent bool   `json:"pending_consent"`
	ConsentID      string `json:"consent_id,omitempty"`
	Message        string `json:"message"`
	Data           any    `json:"data,omitempty"`
}

type Tool interface {
	Name() string
	RequiresConsent(action string) bool
	Run(ctx context.Context, action string, input map[string]any, actor string) (any, error)
}

type Persistence interface {
	CreateConsent(tool, action, payload, actor, platform, channelID string) (store.ConsentRecord, error)
	GetConsent(id string) (store.ConsentRecord, error)
	ResolveConsent(id, status, reason string) error
	ListConsents(status string, limit int) ([]store.ConsentRecord, error)
}