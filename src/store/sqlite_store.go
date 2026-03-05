package store

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/google/uuid"
	_ "modernc.org/sqlite"
)

type SQLiteStore struct {
	db *sql.DB
}

func OpenSQLite(dataDir string) (*SQLiteStore, error) {
	if err := os.MkdirAll(dataDir, 0o700); err != nil {
		return nil, err
	}

	dsn := filepath.Join(dataDir, "agent02.db")
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}

	store := &SQLiteStore{db: db}
	if err := store.init(); err != nil {
		return nil, err
	}
	return store, nil
}

func (s *SQLiteStore) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *SQLiteStore) init() error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS notes (
			id TEXT PRIMARY KEY,
			content TEXT NOT NULL,
			created_by TEXT NOT NULL,
			created_at TEXT NOT NULL
		);`,
		`CREATE TABLE IF NOT EXISTS consents (
			id TEXT PRIMARY KEY,
			tool TEXT NOT NULL,
			action TEXT NOT NULL,
			payload TEXT NOT NULL,
			actor TEXT NOT NULL,
			platform TEXT NOT NULL,
			channel_id TEXT NOT NULL,
			status TEXT NOT NULL,
			reason TEXT NOT NULL,
			created_at TEXT NOT NULL,
			resolved_at TEXT NOT NULL
		);`,
		`CREATE INDEX IF NOT EXISTS idx_consents_status_created ON consents(status, created_at);`,
	}
	for _, stmt := range stmts {
		if _, err := s.db.Exec(stmt); err != nil {
			return err
		}
	}
	return nil
}

func (s *SQLiteStore) AddNote(content, createdBy string) (NoteRecord, error) {
	note := NoteRecord{
		ID:        uuid.NewString(),
		Content:   content,
		CreatedBy: createdBy,
		CreatedAt: time.Now().UTC(),
	}
	_, err := s.db.Exec(
		`INSERT INTO notes (id, content, created_by, created_at) VALUES (?, ?, ?, ?)`,
		note.ID,
		note.Content,
		note.CreatedBy,
		note.CreatedAt.Format(time.RFC3339Nano),
	)
	if err != nil {
		return NoteRecord{}, err
	}
	return note, nil
}

func (s *SQLiteStore) ListNotes(limit int) ([]NoteRecord, error) {
	if limit <= 0 || limit > 100 {
		limit = 25
	}
	rows, err := s.db.Query(
		`SELECT id, content, created_by, created_at FROM notes ORDER BY created_at DESC LIMIT ?`,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]NoteRecord, 0, limit)
	for rows.Next() {
		var n NoteRecord
		var createdAt string
		if err := rows.Scan(&n.ID, &n.Content, &n.CreatedBy, &createdAt); err != nil {
			return nil, err
		}
		t, _ := time.Parse(time.RFC3339Nano, createdAt)
		n.CreatedAt = t
		out = append(out, n)
	}
	return out, rows.Err()
}

func (s *SQLiteStore) CreateConsent(tool, action, payload, actor, platform, channelID string) (ConsentRecord, error) {
	now := time.Now().UTC()
	record := ConsentRecord{
		ID:        uuid.NewString(),
		Tool:      tool,
		Action:    action,
		Payload:   payload,
		Actor:     actor,
		Platform:  platform,
		ChannelID: channelID,
		Status:    "pending",
		Reason:    "",
		CreatedAt: now,
	}
	_, err := s.db.Exec(
		`INSERT INTO consents (id, tool, action, payload, actor, platform, channel_id, status, reason, created_at, resolved_at)
		 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		record.ID,
		record.Tool,
		record.Action,
		record.Payload,
		record.Actor,
		record.Platform,
		record.ChannelID,
		record.Status,
		record.Reason,
		record.CreatedAt.Format(time.RFC3339Nano),
		"",
	)
	if err != nil {
		return ConsentRecord{}, err
	}
	return record, nil
}

func (s *SQLiteStore) ResolveConsent(id, status, reason string) error {
	if status != "approved" && status != "denied" {
		return fmt.Errorf("invalid status: %s", status)
	}
	_, err := s.db.Exec(
		`UPDATE consents SET status = ?, reason = ?, resolved_at = ? WHERE id = ? AND status = 'pending'`,
		status,
		reason,
		time.Now().UTC().Format(time.RFC3339Nano),
		id,
	)
	return err
}

func (s *SQLiteStore) GetConsent(id string) (ConsentRecord, error) {
	var c ConsentRecord
	var createdAt string
	var resolvedAt string
	err := s.db.QueryRow(
		`SELECT id, tool, action, payload, actor, platform, channel_id, status, reason, created_at, resolved_at FROM consents WHERE id = ?`,
		id,
	).Scan(
		&c.ID,
		&c.Tool,
		&c.Action,
		&c.Payload,
		&c.Actor,
		&c.Platform,
		&c.ChannelID,
		&c.Status,
		&c.Reason,
		&createdAt,
		&resolvedAt,
	)
	if err != nil {
		return ConsentRecord{}, err
	}
	c.CreatedAt, _ = time.Parse(time.RFC3339Nano, createdAt)
	if resolvedAt != "" {
		c.ResolvedAt, _ = time.Parse(time.RFC3339Nano, resolvedAt)
	}
	return c, nil
}

func (s *SQLiteStore) ListConsents(status string, limit int) ([]ConsentRecord, error) {
	if limit <= 0 || limit > 200 {
		limit = 50
	}
	rows, err := s.db.Query(
		`SELECT id, tool, action, payload, actor, platform, channel_id, status, reason, created_at, resolved_at
		 FROM consents WHERE status = ? ORDER BY created_at DESC LIMIT ?`,
		status,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]ConsentRecord, 0, limit)
	for rows.Next() {
		var c ConsentRecord
		var createdAt string
		var resolvedAt string
		if err := rows.Scan(
			&c.ID,
			&c.Tool,
			&c.Action,
			&c.Payload,
			&c.Actor,
			&c.Platform,
			&c.ChannelID,
			&c.Status,
			&c.Reason,
			&createdAt,
			&resolvedAt,
		); err != nil {
			return nil, err
		}
		c.CreatedAt, _ = time.Parse(time.RFC3339Nano, createdAt)
		if resolvedAt != "" {
			c.ResolvedAt, _ = time.Parse(time.RFC3339Nano, resolvedAt)
		}
		out = append(out, c)
	}
	return out, rows.Err()
}