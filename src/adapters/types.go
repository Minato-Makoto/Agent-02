package adapters

import "context"

type OutboundSender interface {
	SendText(ctx context.Context, channelID string, text string) error
}

type InboundMessage struct {
	Platform  string
	ChannelID string
	UserID    string
	Text      string
}