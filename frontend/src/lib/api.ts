export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export type ChatSource = { id: number; question: string };

export type ChatStreamEvent =
  | { type: "token"; text: string }
  | {
      type: "done";
      messageId: string;
      escalated: boolean;
      humanOffered: boolean;
      intent: string | null;
      sentiment: number | null;
      sources: ChatSource[];
    };

let sessionIdPromise: Promise<string> | null = null;

export function getSessionId(): Promise<string> {
  if (!sessionIdPromise) {
    sessionIdPromise = fetch(`${API_BASE_URL}/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((res) => res.json())
      .then((data) => data.session_id as string);
  }
  return sessionIdPromise;
}

function parseSseFrame(frame: string): ChatStreamEvent | null {
  let eventName = "message";
  let data = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice("event:".length).trim();
    else if (line.startsWith("data:")) data += line.slice("data:".length).trim();
  }
  if (!data) return null;
  const payload = JSON.parse(data);

  if (eventName === "token") {
    return { type: "token", text: payload.text as string };
  }
  if (eventName === "done") {
    return {
      type: "done",
      messageId: payload.message_id,
      escalated: Boolean(payload.escalated),
      humanOffered: Boolean(payload.human_offered),
      intent: payload.intent ?? null,
      sentiment: payload.sentiment ?? null,
      sources: payload.sources ?? [],
    };
  }
  return null;
}

export async function* streamChat(
  message: string,
  userId: string | undefined,
  signal: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const sessionId = await getSessionId();

  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, user_id: userId || null }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseSseFrame(frame);
      if (event) yield event;
      boundary = buffer.indexOf("\n\n");
    }
  }
}

export async function submitFeedback(
  messageId: string,
  rating: "up" | "down",
): Promise<void> {
  await fetch(`${API_BASE_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message_id: messageId, rating }),
  });
}
