package skills

import (
	"context"
	"fmt"
	"strings"

	"github.com/yourname/agent-02/src/store"
)

type NotesTool struct {
	store *store.SQLiteStore
}

func NewNotesTool(store *store.SQLiteStore) *NotesTool {
	return &NotesTool{store: store}
}

func (t *NotesTool) Name() string {
	return "notes"
}

func (t *NotesTool) RequiresConsent(action string) bool {
	return strings.EqualFold(action, "add")
}

func (t *NotesTool) Run(ctx context.Context, action string, input map[string]any, actor string) (any, error) {
	_ = ctx
	switch strings.ToLower(action) {
	case "add":
		content, _ := input["content"].(string)
		content = strings.TrimSpace(content)
		if content == "" {
			return nil, fmt.Errorf("note content is required")
		}
		note, err := t.store.AddNote(content, actor)
		if err != nil {
			return nil, err
		}
		return note, nil
	case "list":
		notes, err := t.store.ListNotes(25)
		if err != nil {
			return nil, err
		}
		return notes, nil
	default:
		return nil, fmt.Errorf("unsupported action: %s", action)
	}
}