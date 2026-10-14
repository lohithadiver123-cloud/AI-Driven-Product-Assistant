import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { sentiment as sentimentTones } from '../theme';
import { useBusy } from '../context/BusyContext';
import { useWorkspaces } from '../context/WorkspaceContext';
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Select,
  SkeletonTable,
  Toolbar,
} from '../components/ui';

const CATEGORIES = [
  { value: '', label: 'All categories' },
  { value: 'bug_report', label: 'Bug report' },
  { value: 'feature_request', label: 'Feature request' },
  { value: 'performance_issue', label: 'Performance issue' },
  { value: 'general_feedback', label: 'General feedback' },
];

const SENTIMENTS = [
  { value: '', label: 'All sentiments' },
  { value: 'positive', label: 'Positive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'negative', label: 'Negative' },
];

const SOURCES = [
  { value: '', label: 'All sources' },
  { value: 'app_review', label: 'App review' },
  { value: 'support_ticket', label: 'Support ticket' },
  { value: 'survey', label: 'Survey' },
  { value: 'social_media', label: 'Social media' },
  { value: 'email', label: 'Email' },
];

const SENTIMENT_TONE = { positive: 'success', neutral: 'warning', negative: 'danger' };

function stars(rating) {
  const n = Math.min(5, Math.max(1, Math.round(rating)));
  return '★'.repeat(n) + '☆'.repeat(5 - n);
}

/**
 * Feedback — the raw records table.
 *
 * Filters live in one toolbar above the table, not scattered around it. The
 * pipeline actions (clean, categorise) are the page's primary actions and show
 * their progress in the global bar as well as on the button itself.
 */
export default function FeedbackList() {
  const navigate = useNavigate();
  const { begin } = useBusy();

  const { activeId: selectedWorkspace, ready } = useWorkspaces();
  const cachedInitial = selectedWorkspace ? api.getCached('/feedback', { workspace_id: selectedWorkspace, page: 1, limit: 20 }) : null;
  const [items, setItems] = useState(() => cachedInitial?.items || []);
  const [total, setTotal] = useState(() => cachedInitial?.total || 0);
  const [totalPages, setTotalPages] = useState(() => cachedInitial?.total_pages || 1);
  const [page, setPage] = useState(1);
  const [limit] = useState(20);

  const [category, setCategory] = useState('');
  const [sentiment, setSentiment] = useState('');
  const [source, setSource] = useState('');

  const [loading, setLoading] = useState(() => !selectedWorkspace || !cachedInitial);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState(null);
  const [busyAction, setBusyAction] = useState('');

  const fetchFeedback = useCallback(async () => {
    if (!selectedWorkspace) return;
    const params = { workspace_id: selectedWorkspace, page, limit };
    if (category) params.category = category;
    if (sentiment) params.sentiment = sentiment;
    if (source) params.source = source;

    if (!api.getCached('/feedback', params)) {
      setLoading(true);
    }
    setError('');
    try {
      const params = { workspace_id: selectedWorkspace, page, limit };
      if (category) params.category = category;
      if (sentiment) params.sentiment = sentiment;
      if (source) params.source = source;

      const { data } = await api.get('/feedback', { params });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.total_pages || 1);
    } catch {
      setError('Could not load feedback for this workspace.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [selectedWorkspace, page, limit, category, sentiment, source]);

  // No workspace means no query, so clear the flag the table is waiting on.
  useEffect(() => {
    if (ready && !selectedWorkspace) setLoading(false);
  }, [ready, selectedWorkspace]);

  useEffect(() => {
    fetchFeedback();
  }, [fetchFeedback]);

  const runPipeline = async (path, label) => {
    const done = begin(label);
    setBusyAction(path);
    setNotice(null);
    try {
      const body = new FormData();
      body.append('workspace_id', selectedWorkspace);
      const { data } = await api.post(path, body);
      setNotice({ variant: 'success', text: data.message || `${label} finished.` });
      await fetchFeedback();
    } catch (err) {
      setNotice({
        variant: 'error',
        text: `${label} failed: ${err.response?.data?.detail || 'unknown error'}`,
      });
    } finally {
      setBusyAction('');
      done();
    }
  };

  const resetTo = (setter) => (event) => {
    setter(event.target.value);
    setPage(1);
  };

  const filtered = Boolean(category || sentiment || source);

  return (
    <div className="page-container">
      <PageHeader
        icon="inbox"
        title="Feedback"
        trail="insight"
        description="Every imported record. Clean the text, then categorise to unlock themes and sentiment."
        actions={
          <>
            <Button
              variant="outline"
              icon="refresh"
              disabled={!selectedWorkspace}
              loading={busyAction === '/feedback/clean'}
              onClick={() => runPipeline('/feedback/clean', 'Cleaning')}
            >
              Clean text
            </Button>
            <Button
              variant="primary"
              icon="zap"
              disabled={!selectedWorkspace}
              loading={busyAction === '/feedback/categorize'}
              onClick={() => runPipeline('/feedback/categorize', 'Categorising')}
            >
              Categorise
            </Button>
          </>
        }
      />

      {notice && <Alert variant={notice.variant}>{notice.text}</Alert>}
      {error && <Alert variant="error">{error}</Alert>}

      <Toolbar
        left={
          <>
            <Select label="Category" value={category} onChange={resetTo(setCategory)}>
              {CATEGORIES.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                </option>
              ))}
            </Select>

            <Select label="Sentiment" value={sentiment} onChange={resetTo(setSentiment)}>
              {SENTIMENTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>

            <Select label="Source" value={source} onChange={resetTo(setSource)}>
              {SOURCES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </>
        }
        right={
          filtered && (
            <Button
              variant="ghost"
              size="sm"
              icon="x"
              onClick={() => {
                setCategory('');
                setSentiment('');
                setSource('');
                setPage(1);
              }}
            >
              Clear filters
            </Button>
          )
        }
      />

      <Card flush>
        {error && !items.length ? (
          <ErrorState title="Feedback could not be loaded" onRetry={fetchFeedback}>
            The request to the feedback service failed. Your data is untouched.
          </ErrorState>
        ) : loading ? (
          <SkeletonTable rows={8} columns={6} />
        ) : items.length === 0 ? (
          <EmptyState
            icon="inbox"
            title={filtered ? 'No records match these filters' : 'No feedback yet'}
            actions={
              filtered ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setCategory('');
                    setSentiment('');
                    setSource('');
                    setPage(1);
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                <Button variant="primary" icon="download" onClick={() => navigate('/import')}>
                  Import feedback
                </Button>
              )
            }
          >
            {filtered
              ? 'Widen the filters, or clear them to see every record in this workspace.'
              : 'Import a CSV or JSON export and the records will appear here, ready to clean and categorise.'}
          </EmptyState>
        ) : (
          <div className="table-responsive">
            <table className="table">
              <caption className="sr-only">
                {`Feedback items, page ${page} of ${totalPages}`}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Item</th>
                  <th scope="col">Source</th>
                  <th scope="col">Category</th>
                  <th scope="col">Sentiment</th>
                  <th scope="col">Rating</th>
                  <th scope="col">Imported</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item._id}>
                    <td>
                      <div className="table-primary">
                        <strong>{item.title || 'Untitled record'}</strong>
                        {item.content && <span className="table-secondary">{item.content}</span>}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-neutral">
                        {(item.source || 'unknown').replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td>
                      {item.category ? (
                        <span className="badge badge-accent">
                          {item.category.replace(/_/g, ' ')}
                        </span>
                      ) : (
                        <span className="text-light">Not categorised</span>
                      )}
                    </td>
                    <td>
                      {item.sentiment ? (
                        <Badge tone={SENTIMENT_TONE[item.sentiment] || 'neutral'}>
                          {item.sentiment}
                        </Badge>
                      ) : (
                        <span className="text-light">—</span>
                      )}
                    </td>
                    <td>
                      {item.rating ? (
                        <span style={{ color: sentimentTones.neutral.line, letterSpacing: 1 }}>
                          {stars(item.rating)}
                        </span>
                      ) : (
                        <span className="text-light">—</span>
                      )}
                    </td>
                    <td className="text-muted tight">
                      {item.created_at ? new Date(item.created_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {!loading && totalPages > 1 && (
        <div className="pagination">
          <Button
            size="sm"
            icon="arrowLeft"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Previous
          </Button>
          <span className="pagination-info">
            Page {page} of {totalPages} · {total} records
          </span>
          <Button
            size="sm"
            iconRight="arrowRight"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
