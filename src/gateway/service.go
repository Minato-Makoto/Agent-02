package gateway

import (
	"context"
	"fmt"
	"strings"

	"github.com/yourname/agent-02/src/adapters"
	"github.com/yourname/agent-02/src/llm"
	"github.com/yourname/agent-02/src/skills"
	"github.com/yourname/agent-02/src/store"
)

type Service struct {
	llm           *llm.Manager
	skills        *skills.Runner
	skillEnabled  map[string]bool
	db            *store.SQLiteStore
}

func NewService(llmManager *llm.Manager, skillRunner *skills.Runner, db *store.SQLiteStore, skillEnabled map[string]bool) *Service {
	if skillEnabled == nil {
		skillEnabled = map[string]bool{}
	}
	return &Service{
		llm:          llmManager,
		skills:       skillRunner,
		db:           db,
		skillEnabled: skillEnabled,
	}
}

func (s *Service) ProcessInbound(ctx context.Context, msg adapters.InboundMessage) (string, error) {
	input := strings.TrimSpace(msg.Text)
	if input == "" {
		return "", nil
	}

	if strings.HasPrefix(input, "/note add ") {
		if !s.skillEnabled["notes"] {
			return "Notes skill is disabled.", nil
		}
		content := strings.TrimSpace(strings.TrimPrefix(input, "/note add "))
		res, err := s.skills.Execute(ctx, skills.Request{
			Tool:      "notes",
			Action:    "add",
			Input:     map[string]any{"content": content},
			Actor:     msg.UserID,
			Platform:  msg.Platform,
			ChannelID: msg.ChannelID,
		})
		if err != nil {
			return "", err
		}
		if res.PendingConsent {
			return fmt.Sprintf("Consent required. Approve in Control UI with ID: %s", res.ConsentID), nil
		}
		return "Note saved.", nil
	}

	if input == "/note list" {
		if !s.skillEnabled["notes"] {
			return "Notes skill is disabled.", nil
		}
		res, err := s.skills.Execute(ctx, skills.Request{
			Tool:      "notes",
			Action:    "list",
			Input:     map[string]any{},
			Actor:     msg.UserID,
			Platform:  msg.Platform,
			ChannelID: msg.ChannelID,
		})
		if err != nil {
			return "", err
		}
		notes, ok := res.Data.([]store.NoteRecord)
		if !ok || len(notes) == 0 {
			return "No notes found.", nil
		}
		lines := make([]string, 0, len(notes)+1)
		lines = append(lines, "Recent notes:")
		for i, n := range notes {
			if i == 5 {
				break
			}
			lines = append(lines, fmt.Sprintf("%d. %s", i+1, n.Content))
		}
		return strings.Join(lines, "\n"), nil
	}

	if strings.EqualFold(input, "/help") {
		return "Commands: /note add <text>, /note list, /help", nil
	}

	answer, err := s.llm.Generate(ctx, input)
	if err != nil {
		return "", err
	}
	return answer, nil
}

func (s *Service) ApproveConsent(ctx context.Context, consentID string) (skills.Result, error) {
	return s.skills.ApproveConsent(ctx, consentID)
}

func (s *Service) DenyConsent(consentID, reason string) error {
	return s.skills.DenyConsent(consentID, reason)
}

func (s *Service) ListPendingConsents(limit int) ([]any, error) {
	return s.skills.ListPending(limit)
}

func (s *Service) ListNotes(limit int) ([]store.NoteRecord, error) {
	return s.db.ListNotes(limit)
}