import { useEffect, useRef } from 'react';
import MessageBubble from './MessageBubble';

interface UIMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  loading?: boolean;
}

interface Props {
  messages: UIMessage[];
  activeTools: string[];
}

const TOOL_LABELS: Record<string, string> = {
  list_workspaces: 'Listing workspaces',
  list_datasets: 'Listing datasets',
  list_reports: 'Listing reports',
  execute_dax: 'Running DAX query',
  get_tables_and_columns: 'Discovering schema',
  get_measures: 'Finding measures',
  refresh_dataset: 'Refreshing dataset',
};

export default function ChatWindow({ messages, activeTools }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activeTools]);

  return (
    <div className="chat-container">
      {messages.map((msg, i) => (
        <MessageBubble key={i} message={msg} />
      ))}

      {activeTools.length > 0 && (
        <div className="message" style={{ maxWidth: 780, margin: '0 auto' }}>
          <div className="avatar assistant">&#9881;</div>
          <div>
            {activeTools.map((t, i) => (
              <div key={i} className="tool-status">
                <span className="dot" />
                {TOOL_LABELS[t] || t}...
              </div>
            ))}
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
