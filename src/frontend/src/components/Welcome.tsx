interface WelcomeProps {
  onStarterClick: (text: string) => void;
}

const STARTERS = [
  'What workspaces do I have?',
  'Show me datasets in my workspace',
  'What were total sales last quarter?',
  'List all reports available',
  'Show me the schema of my dataset',
];

export default function Welcome({ onStarterClick }: WelcomeProps) {
  return (
    <div className="welcome">
      <h2>Power BI Chat</h2>
      <p>
        Ask questions about your Power BI data in natural language.
        Powered by Azure OpenAI with built-in PII detection and audit logging.
      </p>
      <div className="starters">
        {STARTERS.map(s => (
          <button key={s} className="starter" onClick={() => onStarterClick(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
