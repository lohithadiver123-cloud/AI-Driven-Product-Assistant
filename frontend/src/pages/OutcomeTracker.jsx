import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import Icon from '../components/Icon';
import { useBusy } from '../context/BusyContext';
import { useWorkspaces } from '../context/WorkspaceContext';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  Hint,
  PageHeader,
  Section,
  Select,
  SkeletonPage,
  Toolbar,
  ToolbarField,
} from '../components/ui';

/**
 * Outcomes — what measurably changed between two imports.
 *
 * Every other page in this app argues about what should be built. This one answers
 * the question that follows: between the two times this workspace collected
 * customer feedback, did anything actually move?
 *
 * The comparison is between two imports of the same product, because the import is
 * the timestamp the system already has. Nothing here asks anyone to remember a
 * release date or to edit a CSV, and nothing here invents a metric: complaint
 * volume, ratings, sentiment and health are all measured from the records
 * themselves, and every topic verdict states the threshold it cleared.
 */

const DIRECTION_LABELS = {
  rising: 'Rising',
  falling: 'Falling',
  steady: 'Steady',
  appeared: 'New',
  disappeared: 'Gone',
  insufficient_evidence: 'Too little evidence',
};

const CONFIDENCE_TONES = { high: 'success', medium: 'warning', low: 'neutral' };

const formatDay = (value) => {
  if (!value) return 'undated';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value.slice(0, 10);
  return parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

const signed = (value, digits = 2) => {
  if (value == null) return '—';
  const rounded = Number(value).toFixed(digits);
  return Number(value) > 0 ? `+${rounded}` : rounded;
};

/**
 * A two-point trend line for a metric that moved between the imports.
 *
 * “Product health 62 out of 100” is a number with no direction; the line says
 * which way it went in the space of a few characters. With only a before and an
 * after there is no honesty in drawing a curve, so this is exactly two points.
 */
function Sparkline({ from, to, tone = 'neutral' }) {
  if (from == null || to == null) return null;
  const max = Math.max(Math.abs(from), Math.abs(to), 1);
  const y = (value) => 18 - (value / max) * 14;
  return (
    <svg className={`sparkline is-${tone}`} viewBox="0 0 60 20" width="60" height="20" aria-hidden="true">
      <path d={`M4 ${y(from)} L56 ${y(to)}`} fill="none" stroke="currentColor" strokeWidth="2" />
      <circle cx="4" cy={y(from)} r="2" fill="currentColor" />
      <circle cx="56" cy={y(to)} r="2.5" fill="currentColor" />
    </svg>
  );
}

/** The reading of a movement in plain words, for the strip under each row. */
function topicHeadline(row) {
  return DIRECTION_LABELS[row.direction] || row.direction;
}

export default function OutcomeTracker() {
  const navigate = useNavigate();
  const { begin } = useBusy();
  const { activeId: workspaceId, activeWorkspace, ready } = useWorkspaces();

  const [comparison, setComparison] = useState(() => (workspaceId ? api.getCached(`/outcome/${workspaceId}/compare`) : null));
  const [loading, setLoading] = useState(() => !workspaceId || !api.getCached(`/outcome/${workspaceId}/compare`));
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [beforeId, setBeforeId] = useState('');
  const [afterId, setAfterId] = useState('');

  const load = useCallback(async (id, options = {}) => {
    if (!id) return;
    const query = new URLSearchParams();
    if (options.before || beforeId) query.set('before', options.before || beforeId);
    if (options.after || afterId) query.set('after', options.after || afterId);
    const suffix = query.toString() ? `?${query.toString()}` : '';
    if (!api.getCached(`/outcome/${id}/compare${suffix}`)) {
      setLoading(true);
    }
    setError('');
    try {
      const { data } = await api.get(`/outcome/${id}/compare${suffix}`);
      setComparison(data);
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;
      setError(detail || 'Could not compare this workspace’s imports.');
      setComparison(null);
    } finally {
      setLoading(false);
    }
  }, [beforeId, afterId]);

  useEffect(() => {
    if (workspaceId) {
      setBeforeId('');
      setAfterId('');
      load(workspaceId, { before: '', after: '' });
    }
    // Reloading only when the workspace changes: the selects call load() themselves.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  const exportMarkdown = async () => {
    if (!workspaceId) return;
    setExporting(true);
    setNotice('');
    const done = begin('Exporting the comparison…');
    try {
      const query = new URLSearchParams();
      if (beforeId) query.set('before', beforeId);
      if (afterId) query.set('after', afterId);
      const suffix = query.toString() ? `?${query.toString()}` : '';
      const { data } = await api.get(`/outcome/${workspaceId}/export${suffix}`);
      const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {
        type: 'text/markdown',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'outcome-tracking.md';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice('Comparison exported as Markdown.');
    } catch {
      setError('Could not export the comparison.');
    } finally {
      setExporting(false);
      done();
    }
  };

  const batches = comparison?.batches || [];
  const isReady = comparison?.status === 'ready';
  const themes = comparison?.themes || [];

  // The one number that drives the page, said out loud. A rise in complaints is
  // the bad direction, and it is coloured and worded that way.
  const problemDelta = comparison?.deltas?.problem_per_100 ?? 0;
  const complaintsUp = problemDelta > 0.05;
  const complaintsDown = problemDelta < -0.05;
  const complaintVerb = complaintsUp ? 'rose' : complaintsDown ? 'fell' : 'held steady';
  const complaintDirection = complaintsUp ? 'worse' : complaintsDown ? 'better' : 'flat';
  const complaintTone = `is-${complaintDirection}`;
  const complaintIcon = complaintsUp ? 'alert' : complaintsDown ? 'checkCircle' : 'minus';
  const smallerSide =
    (comparison?.after?.total ?? 0) < (comparison?.before?.total ?? 0) ? 'after' : 'before';
  const largerSideTotal = Math.max(comparison?.after?.total ?? 0, comparison?.before?.total ?? 0);

  return (
    <div className="page-container">
      <PageHeader
        icon="trendingUp"
        title="Outcomes"
        trail="measured"
        description={
          activeWorkspace
            ? `What measurably changed between two imports of ${activeWorkspace.name}.`
            : 'What measurably changed between two imports of this product’s feedback.'
        }
        actions={
          isReady ? (
            <Button variant="outline" icon="download" onClick={exportMarkdown} loading={exporting}>
              Export
            </Button>
          ) : (
            <Button variant="primary" icon="download" onClick={() => navigate('/import')}>
              Import feedback
            </Button>
          )
        }
      />

      {notice && <p className="text-success text-xs">{notice}</p>}

      {loading && ready ? (
        <SkeletonPage />
      ) : error ? (
        <Card>
          <CardBody>
            <ErrorState title="Could not compare imports" onRetry={() => load(workspaceId)}>
              {error}
            </ErrorState>
          </CardBody>
        </Card>
      ) : !isReady ? (
        <Section
          title="Nothing to compare yet"
          hint="Outcome tracking compares two imports of the same workspace, so it needs a second one."
        >
          <Card>
            <CardBody className="stack stack-md">
              <EmptyState icon="flask" title="One import so far">
                Import this product’s feedback again later — a month after a release, or a week after a
                fix ships. The change between the two collections is then measured from the records
                themselves: mentions per 100 records, ratings, sentiment and product health.
              </EmptyState>

              {batches.length > 0 && (
                <div className="table-responsive">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Import</th>
                        <th scope="col">File</th>
                        <th scope="col">Collected</th>
                        <th scope="col">Records</th>
                      </tr>
                    </thead>
                    <tbody>
                      {batches.map((batch) => (
                        <tr key={batch.batch_id}>
                          <td className="text-semibold">{batch.label}</td>
                          <td className="text-muted">{batch.filename || '—'}</td>
                          <td className="text-muted">{formatDay(batch.imported_at)}</td>
                          <td>{batch.stored.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {(comparison?.notes || []).map((note) => (
                <p key={note} className="text-muted text-xs">
                  {note}
                </p>
              ))}

              <div className="row">
                <Button variant="primary" icon="download" onClick={() => navigate('/import')}>
                  Import more feedback
                </Button>
              </div>
            </CardBody>
          </Card>
        </Section>
      ) : (
        <>
          {/*
           * A shaky comparison says so before it says anything else. The
           * numbers below are directional when the later import is small, and
           * burying that in a badge at the bottom invited the wrong reading.
           */}
          {comparison.confidence === 'low' && (
            <Alert variant="warning" title="Treat this as directional">
              {smallerSide === 'after'
                ? `Only ${comparison.after.total.toLocaleString()} records in the later import`
                : `Only ${comparison.before.total.toLocaleString()} records in the earlier import`}
              , against {largerSideTotal.toLocaleString()} in the other. Read the direction, not the exact
              size, of these movements — import more feedback and compare again for a firmer reading.
            </Alert>
          )}

          {/* Who is being compared with whom decides everything below, so the
              two pickers come first, not after the summary they produced. */}
          <Toolbar right="Pick any two imports to compare, not only the two most recent ones.">
            <ToolbarField label="Earlier import" htmlFor="outcome-before">
              <Select
                id="outcome-before"
                value={beforeId || comparison.compared.before.batch_id}
                onChange={(event) => {
                  setBeforeId(event.target.value);
                  load(workspaceId, { before: event.target.value, after: afterId });
                }}
              >
                {batches.map((batch) => (
                  <option key={batch.batch_id} value={batch.batch_id}>
                    {batch.label}
                  </option>
                ))}
              </Select>
            </ToolbarField>
            <ToolbarField label="Later import" htmlFor="outcome-after">
              <Select
                id="outcome-after"
                value={afterId || comparison.compared.after.batch_id}
                onChange={(event) => {
                  setAfterId(event.target.value);
                  load(workspaceId, { before: beforeId, after: event.target.value });
                }}
              >
                {batches.map((batch) => (
                  <option key={batch.batch_id} value={batch.batch_id}>
                    {batch.label}
                  </option>
                ))}
              </Select>
            </ToolbarField>
          </Toolbar>

          <Card>
            <CardBody className="stack stack-md">
              <div className="row row-wrap">
                <Badge tone={CONFIDENCE_TONES[comparison.confidence] || 'neutral'}>
                  {comparison.confidence} confidence
                </Badge>
                <Badge tone="neutral">{comparison.gap_days ?? '—'} days between imports</Badge>
              </div>

              {/* The headline is a sentence, not a pair of numbers with an
                  unexplained “per 100” between them. */}
              <div className={`outcome-headline is-${complaintDirection}`}>
                <Icon name={complaintIcon} size={20} />
                <span>
                  Complaints {complaintVerb} from{' '}
                  <strong>{comparison.before.problem_per_100.toLocaleString()}</strong> to{' '}
                  <strong>{comparison.after.problem_per_100.toLocaleString()}</strong> per{' '}
                  {comparison.method.rate_base} reviews
                  <Hint label="What counts as a complaint">
                    Bug and performance mentions, counted per {comparison.method.rate_base} records so a
                    larger second import cannot look like a rise in everything.
                  </Hint>
                </span>
              </div>

              <div className="metric-strip">
                <div className="metric">
                  <span className="metric-label">Average rating</span>
                  <span className="metric-value">
                    {comparison.after.avg_rating != null ? comparison.after.avg_rating : 'Not rated'}
                  </span>
                  <span
                    className={`metric-delta is-${
                      (comparison.deltas.avg_rating ?? 0) >= 0 ? 'good' : 'bad'
                    }`}
                  >
                    {signed(comparison.deltas.avg_rating)} since the earlier import
                  </span>
                </div>

                <div className="metric">
                  <span className="metric-label">Product health</span>
                  <span className="metric-value">
                    {comparison.after.health_score != null ? comparison.after.health_score : '—'}
                  </span>
                  <Sparkline
                    from={comparison.before.health_score}
                    to={comparison.after.health_score}
                    tone={(comparison.deltas.health_score ?? 0) >= 0 ? 'good' : 'bad'}
                  />
                </div>

                <div className="metric">
                  <span className="metric-label">Records compared</span>
                  <span className="metric-value">{comparison.after.total.toLocaleString()}</span>
                  <span className="metric-delta">
                    vs {comparison.before.total.toLocaleString()} earlier ·{' '}
                    {comparison.gap_days == null ? 'gap unknown' : `${comparison.gap_days} days apart`}
                  </span>
                </div>
              </div>

              <p className="text-muted text-xs" style={{ margin: 0 }}>
                {comparison.compared.before.label} vs {comparison.compared.after.label}. {comparison.headline}
              </p>
            </CardBody>
          </Card>

          <Section
            title="What moved, topic by topic"
            hint="One vocabulary, mined from both imports together, with each record counted in a single topic."
          >
            <Card flush>
              <CardHeader
                title="Topic movement"
                hint="A topic short of the mention floor is reported as such rather than as a trend."
              />
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Topic</th>
                      <th scope="col">Category</th>
                      <th scope="col">Earlier</th>
                      <th scope="col">Later</th>
                      <th scope="col">Per {comparison.method.rate_base}</th>
                      <th scope="col">Reading</th>
                    </tr>
                  </thead>
                  <tbody>
                    {themes.map((row) => (
                      <tr key={row.topic_id}>
                        <td className="text-semibold">{row.title}</td>
                        <td className="text-muted">{row.category.replace(/_/g, ' ')}</td>
                        <td>{row.before_count}</td>
                        <td>{row.after_count}</td>
                        <td className="text-muted">
                          {row.before_per_100} → {row.after_per_100}
                        </td>
                        <td>
                          <div className="row row-wrap">
                            <Badge tone={row.tone}>{topicHeadline(row)}</Badge>
                            <span className="text-muted text-xs">{row.reading}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </Section>

          <Section
            title="How this was measured"
            hint="Stated with the result so the numbers can be checked, not taken on trust."
          >
            <Card>
              <CardBody className="stack stack-md">
                <ul className="stack stack-sm">
                  <li>
                    <strong>Compared unit:</strong> {comparison.method.unit}. The batch of every record is
                    the import it arrived in, so the time axis comes from the data collection itself.
                  </li>
                  <li>
                    <strong>Topic axis:</strong> {comparison.method.topic_axis} — {comparison.method.assignment},
                    so a word several topics share cannot inflate any of them, and the topic counts always
                    add up to the collection.
                  </li>
                  <li>
                    <strong>Normalisation:</strong> {comparison.method.normalisation}, so a larger second
                    collection is not read as a rise in everything.
                  </li>
                  <li>
                    <strong>Thresholds:</strong> a movement is only claimed above{' '}
                    {comparison.method.min_mentions} mentions on both sides and{' '}
                    {comparison.method.min_per_100_delta} per {comparison.method.rate_base} records, or{' '}
                    {Math.round(comparison.method.relative_band * 100)}% of the earlier value — whichever
                    is larger. Anything below that is reported as steady.
                  </li>
                  <li>
                    <strong>Not inferred:</strong> revenue, retention, conversion and crash-free rate are
                    never stated, because this workspace does not measure them.
                  </li>
                </ul>

                {comparison.notes.length > 0 && (
                  <div className="stack stack-sm">
                    <h3 className="card-title">Caveats on this comparison</h3>
                    {comparison.notes.map((note) => (
                      <Alert key={note} variant="warning">
                        {note}
                      </Alert>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>
          </Section>
        </>
      )}
    </div>
  );
}
