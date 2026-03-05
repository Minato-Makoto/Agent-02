package skills

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
)

type Runner struct {
	store Persistence
	tools map[string]Tool
	mu    sync.RWMutex
}

func NewRunner(store Persistence) *Runner {
	return &Runner{
		store: store,
		tools: make(map[string]Tool),
	}
}

func (r *Runner) Register(tool Tool) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.tools[tool.Name()] = tool
}

func (r *Runner) Execute(ctx context.Context, req Request) (Result, error) {
	tool, err := r.lookup(req.Tool)
	if err != nil {
		return Result{}, err
	}

	if tool.RequiresConsent(req.Action) {
		payload, err := json.Marshal(req)
		if err != nil {
			return Result{}, err
		}
		record, err := r.store.CreateConsent(req.Tool, req.Action, string(payload), req.Actor, req.Platform, req.ChannelID)
		if err != nil {
			return Result{}, err
		}
		return Result{
			PendingConsent: true,
			ConsentID:      record.ID,
			Message:        "Action queued. Approval required.",
		}, nil
	}

	data, err := tool.Run(ctx, req.Action, req.Input, req.Actor)
	if err != nil {
		return Result{}, err
	}
	return Result{Message: "Action completed.", Data: data}, nil
}

func (r *Runner) ApproveConsent(ctx context.Context, consentID string) (Result, error) {
	rec, err := r.store.GetConsent(consentID)
	if err != nil {
		return Result{}, err
	}
	if rec.Status != "pending" {
		return Result{}, fmt.Errorf("consent already %s", rec.Status)
	}

	var req Request
	if err := json.Unmarshal([]byte(rec.Payload), &req); err != nil {
		_ = r.store.ResolveConsent(consentID, "denied", "payload parse failed")
		return Result{}, err
	}
	tool, err := r.lookup(req.Tool)
	if err != nil {
		_ = r.store.ResolveConsent(consentID, "denied", "tool unavailable")
		return Result{}, err
	}

	data, err := tool.Run(ctx, req.Action, req.Input, req.Actor)
	if err != nil {
		_ = r.store.ResolveConsent(consentID, "denied", "tool execution failed")
		return Result{}, err
	}
	if err := r.store.ResolveConsent(consentID, "approved", "approved by user"); err != nil {
		return Result{}, err
	}
	return Result{Message: "Action approved and executed.", Data: data}, nil
}

func (r *Runner) DenyConsent(consentID string, reason string) error {
	if reason == "" {
		reason = "denied by user"
	}
	return r.store.ResolveConsent(consentID, "denied", reason)
}

func (r *Runner) ListPending(limit int) ([]any, error) {
	records, err := r.store.ListConsents("pending", limit)
	if err != nil {
		return nil, err
	}
	out := make([]any, 0, len(records))
	for _, rec := range records {
		out = append(out, rec)
	}
	return out, nil
}

func (r *Runner) lookup(name string) (Tool, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	tool, ok := r.tools[name]
	if !ok {
		return nil, fmt.Errorf("unknown tool: %s", name)
	}
	return tool, nil
}