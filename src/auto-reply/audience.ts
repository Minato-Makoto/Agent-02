export type ReplyAudience = "interactive" | "heartbeat" | "background";

export function normalizeReplyAudience(value: unknown): ReplyAudience {
  if (value === "interactive" || value === "heartbeat" || value === "background") {
    return value;
  }
  return "background";
}
