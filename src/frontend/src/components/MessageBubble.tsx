import ReactMarkdown from 'react-markdown';

interface UIMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  loading?: boolean;
}

interface Props {
  message: UIMessage;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      {!isUser && <div className="avatar assistant">AI</div>}
      <div className={`bubble ${isUser ? 'user' : 'assistant'}`}>
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <>
            <ReactMarkdown>{message.content || (message.loading ? 'Thinking...' : '')}</ReactMarkdown>
            {message.toolCalls && message.toolCalls.length > 0 && (
              <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-muted)' }}>
                Tools used: {message.toolCalls.join(', ')}
              </div>
            )}
          </>
        )}
      </div>
      {isUser && <div className="avatar user">You</div>}
    </div>
  );
}
