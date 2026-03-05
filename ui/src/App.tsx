import { useEffect, useMemo, useState } from "react";

type StatusPayload = {
  ok: boolean;
  llm?: { provider: string; model: string };
  connectors?: { telegram: boolean; whatsapp: boolean; discord: boolean };
};

type Consent = {
  id: string;
  tool: string;
  action: string;
  actor: string;
  platform: string;
  channel_id: string;
  created_at: string;
};

type Note = {
  id: string;
  content: string;
  created_by: string;
  created_at: string;
};

async function api<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(init?.headers ?? {}),
  };
  if (token.trim()) {
    headers["X-Agent02-Token"] = token.trim();
  }
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status}`);
  }
  return (await res.json()) as T;
}

export default function App() {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [prompt, setPrompt] = useState("Hello from Agent-02");
  const [reply, setReply] = useState("");
  const [consents, setConsents] = useState<Consent[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const llmSummary = useMemo(() => {
    if (!status?.llm) return "N/A";
    return `${status.llm.provider} · ${status.llm.model}`;
  }, [status]);

  async function loadAll() {
    setError("");
    try {
      const statusPayload = await api<StatusPayload>("/api/status", token);
      setStatus(statusPayload);

      const consentPayload = await api<{ items: Consent[] }>("/api/consents", token);
      setConsents(consentPayload.items || []);

      const notePayload = await api<{ items: Note[] }>("/api/notes", token);
      setNotes(notePayload.items || []);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function sendChat() {
    setBusy(true);
    setError("");
    try {
      const data = await api<{ reply: string }>("/api/chat", token, {
        method: "POST",
        body: JSON.stringify({
          platform: "ui",
          channel_id: "local-ui",
          user_id: "admin",
          message: prompt,
        }),
      });
      setReply(data.reply || "");
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function connectorTest(platform: "telegram" | "whatsapp" | "discord") {
    setBusy(true);
    setError("");
    try {
      await api(`/api/connect/${platform}/test`, token, { method: "POST" });
      setReply(`${platform} connector test succeeded.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approveConsent(id: string) {
    setBusy(true);
    setError("");
    try {
      const data = await api<{ message: string }>(`/api/consents/${id}/approve`, token, { method: "POST" });
      setReply(data.message || "Consent approved.");
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function denyConsent(id: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/api/consents/${id}/deny`, token, {
        method: "POST",
        body: JSON.stringify({ reason: "Denied from Control UI" }),
      });
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h1>Agent-02 Control UI</h1>
          <small className="message">Secure gateway, official APIs only, explicit consent flow.</small>
        </div>
        <span className="badge">LLM {llmSummary}</span>
      </header>

      <section className="panel">
        <label>Admin Token (`X-Agent02-Token`)</label>
        <div className="row">
          <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="Paste admin token" />
          <button className="secondary" onClick={() => void loadAll()} disabled={busy}>
            Refresh
          </button>
        </div>
        {error ? <p className="message" style={{ color: "#ffb4b4" }}>{error}</p> : null}
      </section>

      <div className="grid">
        <section className="panel">
          <h2>Chat Console</h2>
          <label>Prompt</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <div className="row3">
            <button onClick={() => void sendChat()} disabled={busy}>Send</button>
            <button className="secondary" onClick={() => setPrompt("/note add secure integration test")}>Note Add</button>
            <button className="secondary" onClick={() => setPrompt("/note list")}>Note List</button>
          </div>
          <p className="message">{reply}</p>
        </section>

        <section className="panel">
          <h2>Connector Checks</h2>
          <div className="row3">
            <button className="secondary" onClick={() => void connectorTest("telegram")}>Test Telegram</button>
            <button className="secondary" onClick={() => void connectorTest("whatsapp")}>Test WhatsApp</button>
            <button className="secondary" onClick={() => void connectorTest("discord")}>Test Discord</button>
          </div>
          <p className="message">
            Active: TG={String(status?.connectors?.telegram)} WA={String(status?.connectors?.whatsapp)} DS={String(status?.connectors?.discord)}
          </p>
        </section>
      </div>

      <div className="grid">
        <section className="panel">
          <h2>Pending Consents</h2>
          <div className="list">
            {consents.length === 0 ? <div className="item">No pending consent.</div> : null}
            {consents.map((item) => (
              <div className="item" key={item.id}>
                <div className="message">{item.tool}.{item.action} by {item.actor}</div>
                <small>ID: {item.id}</small>
                <div className="row3" style={{ marginTop: "0.5rem" }}>
                  <button className="warn" onClick={() => void approveConsent(item.id)} disabled={busy}>Approve</button>
                  <button className="danger" onClick={() => void denyConsent(item.id)} disabled={busy}>Deny</button>
                  <button className="secondary" onClick={() => navigator.clipboard.writeText(item.id)}>Copy ID</button>
                </div>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2>Notes Skill</h2>
          <div className="list">
            {notes.length === 0 ? <div className="item">No notes.</div> : null}
            {notes.map((note) => (
              <div className="item" key={note.id}>
                <div className="message">{note.content}</div>
                <small>{new Date(note.created_at).toLocaleString()}</small>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}