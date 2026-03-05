package llm

import (
	"context"
	"fmt"
	"strings"

	"github.com/yourname/agent-02/src/config"
	"github.com/yourname/agent-02/src/security"
)

type Manager struct {
	cfg config.LLMConfig
	key []byte
}

func NewManager(cfg config.LLMConfig, key []byte) *Manager {
	return &Manager{cfg: cfg, key: key}
}

func (m *Manager) Generate(ctx context.Context, userMessage string) (string, error) {
	providerName := strings.ToLower(strings.TrimSpace(m.cfg.Provider))
	if providerName == "" {
		providerName = "openai"
	}

	var client ChatClient
	switch providerName {
	case "llama.cpp", "local", "local-gguf":
		apiKey, err := security.DecryptString(m.key, m.cfg.LocalLlamaCPP.APIKeyEnc)
		if err != nil {
			return "", err
		}
		client = NewOpenAICompatClient(m.cfg.LocalLlamaCPP.BaseURL, apiKey, m.cfg.RequestTimeoutSec)
	case "openai", "anthropic", "gemini", "xai", "grok", "deepseek", "qwen":
		apiKey, err := security.DecryptString(m.key, m.cfg.Cloud.APIKeyEnc)
		if err != nil {
			return "", err
		}
		client = NewOpenAICompatClient(m.cfg.Cloud.BaseURL, apiKey, m.cfg.RequestTimeoutSec)
	default:
		return "", fmt.Errorf("unsupported provider: %s", providerName)
	}

	return client.Generate(ctx, ChatRequest{
		SystemPrompt: m.cfg.SystemPrompt,
		UserMessage:  userMessage,
		Model:        m.cfg.Model,
		MaxTokens:    m.cfg.MaxTokens,
		Temperature:  m.cfg.Temperature,
	})
}