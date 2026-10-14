import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import Icon from '../components/Icon';
import { useBusy } from '../context/BusyContext';
import { useWorkspaces } from '../context/WorkspaceContext';
import {
  Alert,
  Badge,
  Button,
  EmptyState,
  IconButton,
  Modal,
  PageHeader,
  Pill,
  Skeleton,
  SkeletonText,
} from '../components/ui';

const STARTER_PROMPTS = [
  'What are users complaining about most?',
  'Which feature has the highest priority score?',
  'Draft a PRD for our top pain point',
  'Break our top feature into user stories',
  'Compare dark mode against performance fixes',
  'Show the harshest negative reviews with quotes',
];

const WELCOME = `### Ask about your own feedback

This workspace's feedback, themes, pain points and PRDs are already loaded. Nothing
here is generic advice — answers cite the records they came from.`;

/**
 * Renders the emphasis the replies use — **bold** and *italic* — wherever it
 * appears in a line. Everything outside those runs stays plain text, so no
 * stray asterisks ever reach the reader.
 */
function inline(text, keyPrefix) {
  return String(text)
    .split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g)
    .filter(Boolean)
    .map((part, index) => {
      const key = `${keyPrefix}-${index}`;
      if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
        return <strong key={key}>{part.slice(2, -2)}</strong>;
      }
      if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
        return <em key={key}>{part.slice(1, -1)}</em>;
      }
      return part;
    });
}

/** Renders the small markdown subset the Copilot replies with. */
function MessageBody({ text }) {
  return (
    <div className="chat-body">
      {String(text)
        .split('\n')
        .map((line, index) => {
          const key = `${index}-${line.slice(0, 12)}`;
          if (line.startsWith('### ')) return <h4 key={key}>{inline(line.slice(4), key)}</h4>;
          if (line.startsWith('## ')) return <h3 key={key}>{inline(line.slice(3), key)}</h3>;
          if (line.startsWith('# ')) return <h3 key={key}>{inline(line.slice(2), key)}</h3>;
          if (line.startsWith('- ')) {
            return (
              <p key={key} className="chat-bullet">
                {inline(line.slice(2), key)}
              </p>
            );
          }
          if (line.startsWith('> ')) {
            return (
              <blockquote key={key} className="chat-quote">
                {inline(line.slice(2), key)}
              </blockquote>
            );
          }
          if (!line.trim()) return <div key={key} className="chat-gap" />;
          return (
            <p key={key} className="chat-line">
              {inline(line, key)}
            </p>
          );
        })}
    </div>
  );
}

function TypingBubble() {
  return (
    <div className="chat-row">
      <span className="chat-avatar">
        <Icon name="sparkle" size={16} />
      </span>
      <div className="chat-bubble is-assistant" role="status" aria-label="Writing a reply">
        <SkeletonText lines={3} />
      </div>
    </div>
  );
}

/**
 * Copilot — grounded chat over one workspace.
 *
 * The page keeps the transcript as the only focal point. Context and controls
 * live in the header and a single line above the composer so nothing competes
 * with the conversation.
 */
export default function CopilotChat() {
  const navigate = useNavigate();
  const { begin } = useBusy();

  const { activeId: workspaceId, ready, error: workspaceError } = useWorkspaces();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [context, setContext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const [actionLoading, setActionLoading] = useState({});
  const [actionDone, setActionDone] = useState({});
  const [actionNotice, setActionNotice] = useState('');

  const bottomRef = useRef(null);

  const loadContext = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/copilot/context/${id}`);
      setContext(data);
    } catch {
      setContext(null);
    }
  }, []);

  const loadHistory = useCallback(async (id) => {
    try {
      const { data } = await api.get(`/copilot/history/${id}`);
      setMessages(
        data.length
          ? data.map((m) => ({
              id: m.id || m._id,
              sender: m.sender,
              text: m.content || m.text,
              sources: m.sources_cited || [],
              followups: m.suggested_followups || [],
              action: m.action_suggested,
            }))
          : [{ id: 'welcome', sender: 'assistant', text: WELCOME }]
      );
    } catch {
      setError('Could not load this conversation.');
    }
  }, []);

  // One effect drives both the first load and every later switch: the thread
  // is per workspace, so moving workspace swaps the conversation.
  useEffect(() => {
    if (!workspaceId) return undefined;
    let cancelled = false;
    Promise.all([loadHistory(workspaceId), loadContext(workspaceId)]).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, loadHistory, loadContext]);

  useEffect(() => {
    if (!ready) return;
    if (!workspaceId) setLoading(false);
    if (workspaceError) setError(workspaceError);
  }, [ready, workspaceId, workspaceError]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, sending]);

  const send = async (preset) => {
    const text = (preset ?? input).trim();
    if (!text || !workspaceId || sending) return;

    const history = messages.slice(-6).map((m) => ({ sender: m.sender, content: m.text }));
    setMessages((prev) => [...prev, { id: `u-${Date.now()}`, sender: 'user', text }]);
    setInput('');
    setSending(true);
    setError('');
    const done = begin('Asking the Copilot');

    try {
      const { data } = await api.post('/copilot/chat', {
        workspace_id: workspaceId,
        message: text,
        session_id: 'default',
        conversation_history: history,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: `a-${Date.now()}`,
          sender: 'assistant',
          text: data.reply,
          sources: data.sources_cited || [],
          followups: data.suggested_followups || [],
          action: data.action_suggested,
        },
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || 'The Copilot did not answer. Check that the API is running.');
      setMessages((prev) => [
        ...prev,
        {
          id: `e-${Date.now()}`,
          sender: 'assistant',
          text: 'The Copilot could not finish that request. Nothing was lost — ask again in a moment.',
          failed: true,
        },
      ]);
    } finally {
      setSending(false);
      done();
    }
  };

  const clearHistory = async () => {
    setConfirmClear(false);
    try {
      await api.delete(`/copilot/history/${workspaceId}`);
      setMessages([{ id: 'welcome-reset', sender: 'assistant', text: WELCOME }]);
    } catch {
      setError('Could not clear this conversation.');
    }
  };

  const runAction = async (action, messageId) => {
    if (!action || !workspaceId) return;
    const type = action.action_type;
    const payload = action.payload || {};

    if (type === 'add_to_backlog') {
      setActionLoading((prev) => ({ ...prev, [messageId]: true }));
      setError('');
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
        setActionNotice(`Added “${payload.name || payload.title || 'initiative'}” to your Prioritization Backlog!`);
      } catch (err) {
        setError(err?.response?.data?.detail || 'Could not add initiative to backlog.');
      } finally {
        setActionLoading((prev) => ({ ...prev, [messageId]: false }));
      }
    } else if (type === 'create_prd') {
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

  // Starter prompts only while the transcript is still basically empty, and
  // only the first few — the rest live in the Composer's own suggestions.
  const isShort = messages.length <= 1;

  return (
    <div className="page-container chat-page">
      <PageHeader
        icon="sparkle"
        title="Copilot"
        description="Grounded in this workspace's own feedback, themes and specs. Every answer cites the records behind it."
        actions={
          <Button
            variant="outline"
            icon="refresh"
            disabled={!workspaceId || sending}
            onClick={() => setConfirmClear(true)}
          >
            Clear chat
          </Button>
        }
      />

      {actionNotice && (
        <Alert variant="success">
          {actionNotice}
        </Alert>
      )}

      {error && (
        <Alert variant="error" title="Request failed">
          {error}
        </Alert>
      )}

      <div className="chat-layout">
        <div className="card chat-window">
          <div className="chat-stream">
            {loading ? (
              <>
                <div className="chat-row">
                  <Skeleton className="skeleton-circle" style={{ width: 28, height: 28 }} />
                  <div className="chat-bubble is-assistant">
                    <SkeletonText lines={4} />
                  </div>
                </div>
                <div className="chat-row is-user">
                  <Skeleton className="skeleton-block" style={{ width: 220, height: 44 }} />
                </div>
              </>
            ) : (
              messages.map((m) => {
                const isUser = m.sender === 'user';
                return (
                  <div key={m.id} className={['chat-row', isUser && 'is-user'].filter(Boolean).join(' ')}>
                    {!isUser && (
                      <span className="chat-avatar" aria-hidden="true">
                        <Icon name="sparkle" size={16} />
                      </span>
                    )}

                    <div className={['chat-bubble', isUser ? 'is-user' : 'is-assistant'].filter(Boolean).join(' ')}>
                      {!isUser && <span className="chat-speaker">Copilot</span>}

                      <MessageBody text={m.text} />

                      {m.sources?.length > 0 && (
                        <div className="chat-sources">
                          <span className="chat-sources-title">
                            <Icon name="link" size={12} /> Sources
                          </span>
                          <div className="row row-wrap">
                            {m.sources.map((source, index) => (
                              <Pill key={`${source.title}-${index}`}>
                                {source.title}
                                {source.detail ? ` — ${source.detail}` : ''}
                              </Pill>
                            ))}
                          </div>
                        </div>
                      )}

                      {m.action && (
                        <div style={{ marginTop: 'var(--sp-2)', display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
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
                          {actionDone[m.id] && (
                            <Button
                              size="sm"
                              variant="ghost"
                              iconRight="arrowRight"
                              onClick={() => navigate('/prioritization')}
                            >
                              View in Backlog
                            </Button>
                          )}
                        </div>
                      )}

                      {m.followups?.length > 0 && (
                        <div className="chat-followups">
                          {m.followups.map((followup) => (
                            <button
                              key={followup}
                              type="button"
                              className="chip"
                              disabled={sending}
                              onClick={() => send(followup)}
                            >
                              {followup}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>

                    {isUser && (
                      <span className="chat-avatar is-user" aria-hidden="true">
                        <Icon name="user" size={16} />
                      </span>
                    )}
                  </div>
                );
              })
            )}

            {sending && <TypingBubble />}
            <div ref={bottomRef} />
          </div>

          {isShort && (
            <div className="chat-starters">
              <span className="text-xs text-muted">Try</span>
              {STARTER_PROMPTS.slice(0, 4).map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  className="chip"
                  disabled={sending || !workspaceId}
                  onClick={() => send(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          )}

          <form
            className="chat-composer"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <label className="sr-only" htmlFor="copilot-input">
              Message the Copilot
            </label>
            <input
              id="copilot-input"
              className="input"
              placeholder="Ask about sentiment, priority, pain points or a spec…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={sending || !workspaceId}
              autoComplete="off"
            />
            <Button
              type="submit"
              variant="primary"
              iconRight="arrowRight"
              loading={sending}
              disabled={!input.trim() || !workspaceId}
            >
              Send
            </Button>
          </form>
        </div>

        <aside className="chat-context">
          <div className="card card-pad stack stack-md">
            <h2 className="card-title">
              <Icon name="layers" size={15} /> In context
            </h2>
            {context ? (
              <ul className="context-list">
                <li>
                  <span className="context-value">{context.total_feedback ?? 0}</span>
                  <span className="context-name">feedback records</span>
                </li>
                <li>
                  <span className="context-value">{context.pain_points?.length ?? 0}</span>
                  <span className="context-name">pain points</span>
                </li>
                <li>
                  <span className="context-value">{context.feature_clusters?.length ?? 0}</span>
                  <span className="context-name">feature clusters</span>
                </li>
                <li>
                  <span className="context-value">{context.existing_prds?.length ?? 0}</span>
                  <span className="context-name">PRD documents</span>
                </li>
                <li>
                  <span className="context-value">{context.prioritization_items?.length ?? 0}</span>
                  <span className="context-name">backlog initiatives</span>
                </li>
                <li>
                  <span className="context-value">{context.roadmap_releases?.length ?? 0}</span>
                  <span className="context-name">roadmap releases</span>
                </li>
              </ul>
            ) : (
              <SkeletonText lines={4} />
            )}
            <hr className="divider" />
            <p className="text-xs text-muted">
              Answers are limited to the records in this workspace. Switch workspaces above to
              change what it can see.
            </p>
          </div>

          <div className="card card-pad stack stack-sm">
            <h2 className="card-title">
              <Icon name="bulb" size={15} /> Ask it to do work
            </h2>
            <p className="text-sm text-muted">
              It can open a draft PRD or a story breakdown for you once it has the context it needs.
            </p>
            <div className="row">
              <Button size="sm" variant="secondary" icon="file" onClick={() => navigate('/prds')}>
                PRD Studio
              </Button>
              <Button size="sm" variant="secondary" icon="clipboard" onClick={() => navigate('/user-stories')}>
                Stories
              </Button>
            </div>
          </div>
        </aside>
      </div>

      <Modal
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Clear this conversation?"
        description="The transcript is permanently deleted. Feedback and documents are untouched."
        icon="refresh"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button variant="danger" icon="trash" onClick={clearHistory}>
              Clear it
            </Button>
          </>
        }
      >
        <div className="modal-body stack stack-sm">
          <p className="prose">
            {messages.filter((m) => !m.id.includes('welcome')).length} messages will be removed from
            this workspace's history.
          </p>
          <Badge tone="neutral">
            <Icon name="clock" size={12} /> Not reversible
          </Badge>
        </div>
      </Modal>
    </div>
  );
}
