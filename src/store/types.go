package store

import "time"

type ConsentRecord struct {
	ID        string    `json:"id"`
	Tool      string    `json:"tool"`
	Action    string    `json:"action"`
	Payload   string    `json:"payload"`
	Actor     string    `json:"actor"`
	Platform  string    `json:"platform"`
	ChannelID string    `json:"channel_id"`
	Status    string    `json:"status"`
	Reason    string    `json:"reason,omitempty"`
	CreatedAt time.Time `json:"created_at"`
	ResolvedAt time.Time `json:"resolved_at,omitempty"`
}

type NoteRecord struct {
	ID        string    `json:"id"`
	Content   string    `json:"content"`
	CreatedBy string    `json:"created_by"`
	CreatedAt time.Time `json:"created_at"`
}