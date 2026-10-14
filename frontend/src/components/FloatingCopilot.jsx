import { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import api from '../services/api';
import Icon from '../components/Icon';
import { Alert, Button, IconButton, Spinner } from './ui';
import { useWorkspaces } from '../context/WorkspaceContext';

const WELCOME =
  'Ask me anything about this workspace — the loudest complaints, the highest-scoring feature, or what to cut.';

function MessageBody({ text }) {
  return (
    <div className="chat-body">
      {String(text)
        .split('\n')
        .map((line, index) => {
          const key = `${index}-${line.slice(0, 10)}`;
          if (line.startsWith('### ')) return <h4 key={key}>{line.slice(4)}</h4>;
          if (line.startsWith('- ')) {
            return (
              <p key={key} className="chat-bullet">
                {line.slice(2)}
              </p>
            );
          }
          if (!line.trim()) return <div key={key} className="chat-gap" />;
          return (
            <p key={key} className="chat-line">
              {line}
            </p>
          );
        })}
    </div>
  );
}

/**
 * Floating Copilot — the compact companion to /copilot.
 *
 * Hidden on the auth screens and on the full-page chat, where it would be a
 * second copy of the same control. It stays mounted across routes, so every
 * hook is declared before the early return that hides it.
 */
export default function FloatingCopilot() {
  const location = useLocation();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { id: 'welcome', sender: 'assistant', text: WELCOME },
  ]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState({});
  const [actionDone, setActionDone] = useState({});

  // Read from the provider rather than localStorage so the thread follows a
  // workspace switch made on the page underneath.
  const { activeId: workspaceId } = useWorkspaces();
  const bottomRef = useRef(null);

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, open, sending]);

  const hidden = ['/', '/register', '/copilot'].includes(location.pathname);
  if (hidden) return null;

  const send = async (event) => {
    event.preventDefault();
    const text = input.trim();
    if (!text || sending || !workspaceId) return;

    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, sender: 'user', text }]);
    setInput('');
    setSending(true);
    setError('');

    try {
      const { data } = await api.post('/copilot/chat', {
        workspace_id: workspaceId,
        message: text,
        session_id: 'floating',
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: 'assistant',
          text: data.reply,
          sources: data.sources_cited || [],
          action: data.action_suggested,
        },
      ]);
    } catch {
      setError('No answer came back. The API may be offline.');
    } finally {
      setSending(false);
    }
  };

  const runAction = async (action, messageId) => {
    if (!action || !workspaceId) return;
    const type = action.action_type;
    const payload = action.payload || {};

    if (type === 'add_to_backlog') {
      setActionLoading((prev) => ({ ...prev, [messageId]: true }));
      try {
        await api.post('/prioritization/item', {
          workspace_id: workspaceId,
          name: payload.name || payload.title || 'New Initiative',
          description: payload.description || payload.prompt || '',
          category: payload.category || 'feature_request',
          reach: Number(payload.reach) || 1000,
          impact: Number(payload.impact) || 2.0,
          confidence: Number(payload.confidence) || 0.8,
          effort: Number(payload.effort) || 2.0,
          value: Number(payload.value) || 7.5,
          moscow: payload.moscow || 'should_have',
        });
        setActionDone((prev) => ({ ...prev, [messageId]: true }));
      } catch (err) {
        setError(err?.response?.data?.detail || 'Could not add initiative.');
      } finally {
        setActionLoading((prev) => ({ ...prev, [messageId]: false }));
      }
    } else if (type === 'create_prd') {
      setOpen(false);
      navigate('/prds', {
        state: {
          prefill: {
            title: payload.title || (payload.name ? `PRD: ${payload.name}` : ''),
            prompt: payload.prompt || payload.description || '',
            sourceType: payload.pain_point_id ? 'pain_point' : (payload.feature_cluster_id ? 'cluster' : (payload.sourceType === 'feature_cluster' ? 'cluster' : payload.sourceType || 'custom')),
            painPointId: payload.pain_point_id || '',
            clusterId: payload.feature_cluster_id || payload.clusterId || '',
            audience: payload.audience || '',
            tone: payload.tone || 'comprehensive',
          },
        },
      });
    } else if (type === 'generate_stories') {
      setOpen(false);
      navigate('/user-stories', {
        state: {
          prefill: {
            source: payload.prd_id ? 'prd' : (payload.cluster_id ? 'cluster' : 'custom'),
            prompt: payload.prompt || payload.title || payload.description || '',
            prdId: payload.prd_id || '',
            clusterId: payload.cluster_id || '',
            count: payload.count || 5,
            persona: payload.persona || 'User',
          },
        },
      });
    }
  };

  if (!open) {
    return (
      <div className="floating-copilot-container">
        <button
          type="button"
          className="floating-copilot-btn"
          onClick={() => setOpen(true)}
          aria-expanded={false}
        >
          <Icon name="sparkle" size={15} />
          Copilot
        </button>
      </div>
    );
  }

  return (
    <div className="floating-copilot-container">
      <section className="floating-chat-drawer" aria-label="Copilot chat">
        <header className="floating-chat-header">
          <div className="floating-chat-title">
            <Icon name="sparkle" size={15} />
            <div>
              <strong>Copilot</strong>
              <span className="floating-chat-sub">
                {workspaceId ? 'Using this workspace' : 'Pick a workspace first'}
              </span>
            </div>
          </div>
          <div className="row">
            <IconButton
              icon="external"
              size="sm"
              label="Open the full Copilot page"
              className="btn-on-dark"
              onClick={() => {
                setOpen(false);
                navigate('/copilot');
              }}
            />
            <IconButton
              icon="x"
              size="sm"
              label="Close chat"
              className="btn-on-dark"
              onClick={() => setOpen(false)}
            />
          </div>
        </header>

        <div className="floating-chat-stream">
          {messages.map((m) => (
            <div key={m.id} className={['chat-row', m.sender === 'user' && 'is-user'].filter(Boolean).join(' ')}>
              <div className={['chat-bubble', m.sender === 'user' ? 'is-user' : 'is-assistant', 'is-compact'].filter(Boolean).join(' ')}>
                <MessageBody text={m.text} />
                {m.action && (
                  <div style={{ marginTop: 'var(--sp-2)' }}>
                    <Button
                      size="sm"
                      variant={actionDone[m.id] ? 'outline' : 'primary'}
                      icon={actionDone[m.id] ? 'check' : (m.action.action_type === 'add_to_backlog' ? 'plus' : 'zap')}
                      disabled={actionDone[m.id] || actionLoading[m.id]}
                      loading={actionLoading[m.id]}
                      onClick={() => runAction(m.action, m.id)}
                    >
                      {actionDone[m.id] ? 'Added to Backlog ✓' : (m.action.label || 'Take Action')}
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {sending && (
            <div className="chat-row">
              <div className="chat-bubble is-assistant is-compact">
                <Spinner size="sm" />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="floating-chat-error">
            <Alert variant="error">{error}</Alert>
          </div>
        )}

        <form className="floating-chat-input-row" onSubmit={send}>
          <label className="sr-only" htmlFor="floating-copilot-input">
            Message the Copilot
          </label>
          <input
            id="floating-copilot-input"
            className="input"
            placeholder="Ask a question…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={sending || !workspaceId}
            autoComplete="off"
          />
          <Button
            type="submit"
            variant="primary"
            size="sm"
            icon="arrowRight"
            loading={sending}
            disabled={!input.trim() || !workspaceId}
            aria-label="Send message"
          />
        </form>
      </section>
    </div>
  );
}
