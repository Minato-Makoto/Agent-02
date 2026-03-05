package llm

import "context"

type ChatRequest struct {
	SystemPrompt string
	UserMessage  string
	Model        string
	MaxTokens    int
	Temperature  float64
}

type ChatClient interface {
	Generate(ctx context.Context, req ChatRequest) (string, error)
}