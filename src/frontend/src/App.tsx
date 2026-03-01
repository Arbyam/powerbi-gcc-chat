import { useState, useRef, useEffect, useCallback } from 'react';
import ChatWindow from './components/ChatWindow';
import Welcome from './components/Welcome';
import { ChatMessage, streamChat } from './services/api';

interface UIMessage {
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: string[];
  loading?: boolean;
}

export default function App() {
  const [messages, setMessages] = useState<UIMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeTools, setActiveTools] = useState<string[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(async (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isLoading) return;

    const userMsg: UIMessage = { role: 'user', content: msg };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setActiveTools([]);

    // Add a placeholder for the assistant response
    setMessages(prev => [...prev, { role: 'assistant', content: '', loading: true }]);

    try {
      const chatMessages: ChatMessage[] = [
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: msg },
      ];

      let fullContent = '';
      const tools: string[] = [];

      for await (const event of streamChat(chatMessages)) {
        if (event.type === 'token' && event.content) {
          fullContent += event.content;
          setMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = { role: 'assistant', content: fullContent, loading: true };
            return updated;
          });
        } else if (event.type === 'tool_call' && event.tool) {
          tools.push(event.tool);
          setActiveTools([...tools]);
        } else if (event.type === 'done') {
          setMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: 'assistant',
              content: fullContent,
              toolCalls: event.tools_called,
              loading: false,
            };
            return updated;
          });
        } else if (event.type === 'error') {
          setMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              role: 'assistant',
              content: event.message || 'An error occurred.',
              loading: false,
            };
            return updated;
          });
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `Error: ${err instanceof Error ? err.message : 'Unknown error'}`,
          loading: false,
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
      setActiveTools([]);
    }
  }, [input, isLoading, messages]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [input]);

  return (
    <>
      <header className="header">
        <h1>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Power BI Chat
          <span className="badge">GCC Ready</span>
        </h1>
      </header>

      {messages.length === 0 ? (
        <Welcome onStarterClick={handleSend} />
      ) : (
        <ChatWindow messages={messages} activeTools={activeTools} />
      )}

      <div className="input-area">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your Power BI data..."
            rows={1}
            disabled={isLoading}
          />
          <button onClick={() => handleSend()} disabled={isLoading || !input.trim()}>
            {isLoading ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </>
  );
}
