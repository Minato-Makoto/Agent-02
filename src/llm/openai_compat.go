package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

type OpenAICompatClient struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

type openAIRequest struct {
	Model       string           `json:"model"`
	Messages    []openAIMessage  `json:"messages"`
	MaxTokens   int              `json:"max_tokens,omitempty"`
	Temperature float64          `json:"temperature,omitempty"`
}

type openAIMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type openAIResponse struct {
	Choices []struct {
		Message openAIMessage `json:"message"`
	} `json:"choices"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error,omitempty"`
}

func NewOpenAICompatClient(baseURL, apiKey string, timeoutSec int) *OpenAICompatClient {
	if timeoutSec <= 0 {
		timeoutSec = 45
	}
	return &OpenAICompatClient{
		baseURL: strings.TrimSuffix(baseURL, "/"),
		apiKey:  apiKey,
		httpClient: &http.Client{
			Timeout: time.Duration(timeoutSec) * time.Second,
		},
	}
}

func (c *OpenAICompatClient) Generate(ctx context.Context, req ChatRequest) (string, error) {
	payload := openAIRequest{
		Model: req.Model,
		Messages: []openAIMessage{
			{Role: "system", Content: req.SystemPrompt},
			{Role: "user", Content: req.UserMessage},
		},
		MaxTokens:   req.MaxTokens,
		Temperature: req.Temperature,
	}

	buf := &bytes.Buffer{}
	if err := json.NewEncoder(buf).Encode(payload); err != nil {
		return "", err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/chat/completions", buf)
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	if c.apiKey != "" {
		httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)
	}

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 2*1024*1024))

	if resp.StatusCode >= 300 {
		return "", fmt.Errorf("model endpoint %s: %s", resp.Status, strings.TrimSpace(string(body)))
	}

	var parsed openAIResponse
	if err := json.Unmarshal(body, &parsed); err != nil {
		return "", err
	}
	if parsed.Error != nil {
		return "", fmt.Errorf("provider error: %s", parsed.Error.Message)
	}
	if len(parsed.Choices) == 0 {
		return "", fmt.Errorf("provider returned empty choices")
	}
	return strings.TrimSpace(parsed.Choices[0].Message.Content), nil
}