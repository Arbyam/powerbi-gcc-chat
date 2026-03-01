const API_BASE = '/api';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  response: string;
  tools_called: string[];
  conversation_id: string | null;
}

export interface StreamEvent {
  type: 'token' | 'tool_call' | 'done' | 'error';
  content?: string;
  tool?: string;
  tools_called?: string[];
  message?: string;
}

export async function sendChat(messages: ChatMessage[], conversationId?: string): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, conversation_id: conversationId, stream: false }),
  });
  if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
  return resp.json();
}

export async function* streamChat(
  messages: ChatMessage[],
  conversationId?: string,
): AsyncGenerator<StreamEvent> {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, conversation_id: conversationId, stream: true }),
  });
  if (!resp.ok) throw new Error(`Chat failed: ${resp.status}`);
  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop()!;
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          yield JSON.parse(line.slice(6));
        } catch { /* skip malformed */ }
      }
    }
  }
}

export async function getHealth(): Promise<{ status: string; version: string; cloud_environment: string }> {
  const resp = await fetch(`${API_BASE}/health`);
  return resp.json();
}

export async function getWorkspaces(): Promise<{ workspaces: Array<{ id: string; name: string }> }> {
  const resp = await fetch(`${API_BASE}/workspaces`);
  return resp.json();
}
