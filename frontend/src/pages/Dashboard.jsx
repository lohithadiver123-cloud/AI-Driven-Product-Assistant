import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import { CategoryPieChart, SentimentDonutChart } from '../components/Charts';
import { sentiment, getCategoryColor, tint } from '../theme';
import { useWorkspaces } from '../context/WorkspaceContext';
import useAnalysisStatus from '../hooks/useAnalysisStatus';
import {
  Alert,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  Hint,
  Menu,
  PageHeader,
  ProgressBar,
  SkeletonChart,
  SkeletonStatGrid,
  Stat,
  StatGrid,
} from '../components/ui';

const SENTIMENT_TONE = { positive: 'success', neutral: 'warning', negative: 'danger' };

/*
 * One colour per meaning, app-wide: severity always reads danger/warning/calm,
 * demand always reads accent/warning/quiet. Two badges never disagree about
 * what red means just because they live on different pages.
 */
const SEVERITY_TONE = { high: 'danger', medium: 'warning', low: 'success' };
const DEMAND_TONE = { high: 'accent', medium: 'warning', low: 'neutral' };

function stars(rating) {
  const n = Math.min(5, Math.max(1, Math.round(rating)));
  return '★'.repeat(n) + '☆'.repeat(5 - n);
}

/**
 * Dashboard — the "where do we stand" screen.
 *
 * Reads top to bottom as one argument: how much feedback (stats), what it is
 * about (category mix), how people feel (sentiment), how processed it is, and
 * the newest raw items. One primary action: go to Insights.
 */
export default function Dashboard() {
  const navigate = useNavigate();

  const { activeId: selectedWorkspace, ready, createWorkspace } = useWorkspaces();
  const [stats, setStats] = useState(() => (selectedWorkspace ? api.getCached(`/workspaces/${selectedWorkspace}/stats`) : null));
  const [recentFeedback, setRecentFeedback] = useState(() => (selectedWorkspace ? api.getCached('/feedback', { workspace_id: selectedWorkspace, limit: 6, page: 1 })?.items || [] : []));
  const [insights, setInsights] = useState(() => (selectedWorkspace ? api.getCached(`/insights/${selectedWorkspace}`) : null));
  const [loading, setLoading] = useState(() => !selectedWorkspace || !api.getCached(`/workspaces/${selectedWorkspace}/stats`));
  const [error, setError] = useState('');
  const [reanalyzing, setReanalyzing] = useState(false);
  const [reanalyzeSuccess, setReanalyzeSuccess] = useState(false);

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState('');
  const [creating, setCreating] = useState(false);

  // With no workspace to open there is no stats request either, so nothing
  // else would ever clear the initial loading flag.
  useEffect(() => {
    if (ready && !selectedWorkspace) setLoading(false);
  }, [ready, selectedWorkspace]);

  useEffect(() => {
    if (!selectedWorkspace) return undefined;
    let cancelled = false;

    (async () => {
      // Only show full skeleton if we have no cached data at all
      if (!api.getCached(`/workspaces/${selectedWorkspace}/stats`)) {
        setLoading(true);
      }
      setError('');
      try {
        const [statsRes, feedbackRes, insightsRes] = await Promise.allSettled([
          api.get(`/workspaces/${selectedWorkspace}/stats`),
          api.get('/feedback', { params: { workspace_id: selectedWorkspace, limit: 6, page: 1 } }),
          api.get(`/insights/${selectedWorkspace}`),
        ]);
        if (cancelled) return;
        if (statsRes.status === 'fulfilled') {
          setStats(statsRes.value.data);
        } else {
          setError('Could not load this workspace’s stats.');
        }
        if (feedbackRes.status === 'fulfilled') {
          setRecentFeedback(feedbackRes.value.data?.items || []);
        }
        if (insightsRes.status === 'fulfilled') {
          setInsights(insightsRes.value.data);
        } else {
          setInsights(null);
        }
      } catch {
        if (!cancelled) setError('Could not load this workspace’s data.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedWorkspace]);

  // Analysis runs on the server — including the one an import queues for itself. This
  // watches it and swaps the numbers in the moment it lands.
  const { status: analysis, run: runAnalysisJob } = useAnalysisStatus(
    selectedWorkspace,
    async (finalStatus) => {
      if (finalStatus.state === 'failed') {
        setError(finalStatus.error || 'Analysis failed. Please try again.');
        return;
      }
      const [statsRes, insightsRes] = await Promise.allSettled([
        api.get(`/workspaces/${selectedWorkspace}/stats`),
        api.get(`/insights/${selectedWorkspace}`),
      ]);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value.data);
      if (insightsRes.status === 'fulfilled') setInsights(insightsRes.value.data);
      setReanalyzeSuccess(true);
      setTimeout(() => setReanalyzeSuccess(false), 4000);
    }
  );

  const analysisRunning = reanalyzing || analysis?.state === 'running';

  const handleReanalyze = async () => {
    if (!selectedWorkspace || reanalyzing) return;
    setReanalyzing(true);
    setReanalyzeSuccess(false);
    setError('');
    try {
      // Queued, not awaited: the run happens on the server and the watcher below swaps
      // the numbers in when it finishes.
      await runAnalysisJob();
    } catch {
      setError('Analysis could not be started. Please try again.');
    } finally {
      setReanalyzing(false);
    }
  };

  const handleCreateWorkspace = async () => {
    if (!newWorkspaceName.trim()) return;
    setCreating(true);
    try {
      // The provider creates it and makes it active, so the page below
      // immediately reads the workspace that was just made.
      await createWorkspace(newWorkspaceName);
      setNewWorkspaceName('');
      setShowCreateForm(false);
    } catch {
      setError('Could not create that workspace.');
    } finally {
      setCreating(false);
    }
  };

  const total = stats?.total_feedback || 0;
  const cleaned = stats?.cleaned_count || 0;
  const categorized = stats?.categorized_count || 0;
  const positive = stats?.by_sentiment?.positive || 0;
  const positivePercent = total > 0 ? Math.round((positive / total) * 1000) / 10 : 0;
  const pct = (value) => (total > 0 ? Math.round((value / total) * 100) : 0);

  const healthScore =
    insights && insights.total_analyzed > 0 && insights.health_score != null
      ? Math.round(insights.health_score * 10) / 10
      : null;
  const painPoints = insights?.pain_points || [];
  const topPainPoints = painPoints.slice(0, 3);
  const urgentPainPoint = painPoints[0] || null;
  const clusters = insights?.feature_clusters || [];
  const topClusters = clusters.slice(0, 3);

  return (
    <div className="page-container">
      <PageHeader
        icon="layout"
        title="Dashboard"
        trail="insight"
        description="What to act on first in this workspace."
        actions={
          <>
            <Button
              variant="outline"
              icon={showCreateForm ? 'x' : 'plus'}
              onClick={() => setShowCreateForm((v) => !v)}
            >
              {showCreateForm ? 'Cancel' : 'New workspace'}
            </Button>

            <Menu
              label="More actions"
              items={[
                { label: 'Import feedback', icon: 'download', onSelect: () => navigate('/import') },
                { label: 'Browse all feedback', icon: 'inbox', onSelect: () => navigate('/feedback') },
              ]}
            />

            {selectedWorkspace && (
              <Button
                variant="outline"
                icon="refresh-cw"
                loading={analysisRunning}
                disabled={analysisRunning}
                onClick={handleReanalyze}
                title="Re-run AI analysis to refresh pain points, quotes and clusters"
              >
                {analysisRunning ? 'Analysing…' : reanalyzeSuccess ? '✓ Done' : 'Re-run Analysis'}
              </Button>
            )}

            <Button variant="primary" onClick={() => navigate('/insights')}>
              Review insights
            </Button>
          </>
        }
      />

      {showCreateForm && (
        <Card>
          <CardBody>
            <div className="row">
              <label className="field-label sr-only" htmlFor="new-workspace">
                New workspace name
              </label>
              <input
                id="new-workspace"
                className="input flex-1"
                placeholder="Workspace name, e.g. Q4 Store Feedback"
                value={newWorkspaceName}
                onChange={(e) => setNewWorkspaceName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateWorkspace()}
                autoFocus
              />
              <Button
                variant="primary"
                loading={creating}
                disabled={!newWorkspaceName.trim()}
                onClick={handleCreateWorkspace}
              >
                Create
              </Button>
            </div>
          </CardBody>
        </Card>
      )}

      {error && <Alert variant="error">{error}</Alert>}
      {analysis?.state === 'running' && (
        <Alert variant="info" title="Analysing this workspace">
          <div className="stack stack-sm">
            <span className="text-sm">
              {analysis.stage_label || 'Working'}
              {analysis.progress ? ` · ${analysis.progress}%` : ''}
            </span>
            <ProgressBar value={analysis.progress ?? null} label={analysis.stage_label || 'Analysis progress'} />
          </div>
        </Alert>
      )}
      {reanalyzeSuccess && (
        <Alert variant="success">
          ✓ Analysis complete — pain points and quotes have been refreshed.
        </Alert>
      )}

      {loading ? (
        <>
          <SkeletonStatGrid count={3} />
          <SkeletonChart label="Loading dashboard data" />
        </>
      ) : total === 0 ? (
        <Card>
          <EmptyState
            icon="inbox"
            title="No feedback in this workspace yet"
            actions={
              <Button variant="primary" icon="download" onClick={() => navigate('/import')}>
                Import feedback
              </Button>
            }
          >
            Import a CSV or JSON export of customer reviews, tickets or survey answers and this page
            fills in automatically.
          </EmptyState>
        </Card>
      ) : (
        <>
          {/* Executive Pulse Hero Card */}
          <Card className="hero-urgency-card">
            <CardBody className="stack stack-sm" style={{ padding: 'var(--sp-3) var(--sp-4)' }}>
              <div className="row row-between row-wrap" style={{ alignItems: 'flex-start' }}>
                <div className="stack stack-xs">
                  <div className="row" style={{ gap: 'var(--sp-2)' }}>
                    <Badge tone="accent" icon="sparkle" className="badge-sm">
                      Executive Pulse
                    </Badge>
                    {healthScore != null && (
                      <Badge tone={healthScore >= 70 ? 'success' : healthScore >= 50 ? 'warning' : 'danger'} className="badge-sm">
                        Health {healthScore}/100
                      </Badge>
                    )}
                    <span className="text-xs text-muted">
                      {total.toLocaleString()} total signals
                    </span>
                  </div>
                  <h2 style={{ fontSize: 'var(--fs-md)', fontWeight: 700, margin: '2px 0 0', color: 'var(--text)' }}>
                    {urgentPainPoint
                      ? `Urgent: ${urgentPainPoint.title}`
                      : `Customer Sentiment: ${positivePercent}% Positive`}
                  </h2>
                  <p className="text-sm text-muted" style={{ margin: 0, maxWidth: '75ch' }}>
                    {urgentPainPoint?.description ||
                      `Analyzing ${total.toLocaleString()} customer feedback items across reviews and support signals.`}
                  </p>
                </div>

                {/*
                 * Supporting actions only. The screen already has one filled
                 * button — “Review insights” in the header — and a second one
                 * here would make the page ask for two decisions at once.
                 */}
                <div className="row" style={{ gap: 'var(--sp-2)' }}>
                  {urgentPainPoint && (
                    <Button
                      variant="outline"
                      size="sm"
                      icon="file"
                      onClick={() =>
                        navigate('/prds', {
                          state: {
                            prefill: {
                              sourceType: 'pain_point',
                              painPointId: urgentPainPoint.id,
                              title: `Resolve: ${urgentPainPoint.title}`,
                              prompt: urgentPainPoint.description || urgentPainPoint.recommended_action || '',
                            },
                          },
                        })
                      }
                    >
                      Draft solution PRD
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    icon="target"
                    onClick={() => navigate('/prioritization')}
                  >
                    Prioritize
                  </Button>
                </div>
              </div>

              {urgentPainPoint?.sample_quotes?.length > 0 && (
                <div
                  style={{
                    padding: '4px 10px',
                    background: 'var(--bg-subtle)',
                    borderRadius: 'var(--radius)',
                    borderLeft: '3px solid var(--danger)',
                    fontSize: 'var(--fs-xs)',
                    color: 'var(--text-soft)',
                    fontStyle: 'italic',
                    marginTop: '2px',
                  }}
                >
                  “{urgentPainPoint.sample_quotes[0]}”
                </div>
              )}
            </CardBody>
          </Card>

          <StatGrid>
            <Stat label="Feedback items" value={total.toLocaleString()} icon="inbox" featured />
            <Stat
              label="Customer Health"
              value={healthScore != null ? `${healthScore}/100` : `${positivePercent}%`}
              hint={healthScore != null ? 'Derived from rating & tone' : `${positive.toLocaleString()} positive`}
            />
            <Stat
              label="Categorised"
              value={`${pct(categorized)}%`}
              hint={`${categorized.toLocaleString()} of ${total.toLocaleString()}`}
            />
          </StatGrid>

          {/* 2-Column Action Hub: Top Pain Points vs Top Opportunities */}
          <div className="grid grid-2">
            <Card>
              <CardHeader
                title="Top Customer Pain Points"
                hint="Voice of customer issues ranked by impact and frequency"
                actions={
                  painPoints.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      iconRight="arrowRight"
                      onClick={() => navigate('/insights')}
                    >
                      View all ({painPoints.length})
                    </Button>
                  )
                }
              />
              <CardBody className="stack stack-sm" style={{ padding: 'var(--sp-3)' }}>
                {topPainPoints.length === 0 ? (
                  <EmptyState icon="target" title="No pain points extracted yet">
                    Run analysis in Insights to detect recurring customer grievances.
                  </EmptyState>
                ) : (
                  topPainPoints.map((pp, idx) => (
                    <div
                      key={pp.id || idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 'var(--sp-3)',
                        padding: 'var(--sp-2) var(--sp-3)',
                        borderRadius: 'var(--radius)',
                        background: 'var(--bg-subtle)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      <div className="stack stack-xs flex-1">
                        <div className="row" style={{ gap: 'var(--sp-2)' }}>
                          <span className={`rank-pill rank-${idx + 1}`}>#{idx + 1}</span>
                          <Badge tone={SEVERITY_TONE[pp.severity] || 'neutral'} className="badge-sm">{pp.severity}</Badge>
                          <strong className="text-sm" style={{ color: 'var(--text)' }}>
                            {pp.title}
                          </strong>
                        </div>
                        {pp.sample_quotes?.[0] ? (
                          <span className="text-xs text-muted clamp-1" style={{ fontStyle: 'italic' }}>
                            “{pp.sample_quotes[0]}”
                          </span>
                        ) : (
                          <span className="text-xs text-muted clamp-1">{pp.description}</span>
                        )}
                        <span className="text-xs text-light row" style={{ gap: 'var(--sp-1)' }}>
                          Impact {pp.impact_score}/100 · {pp.affected_users_count || 0} reviews
                          <Hint label="How impact is scored">
                            Volume (35%) + low rating (25%) + share negative (25%) + bug reports (15%),
                            scaled to 100. High volume alone will not top this list.
                          </Hint>
                        </span>
                      </div>
                      <div className="row" style={{ gap: 'var(--sp-1)', flexShrink: 0 }}>
                        <Button
                          variant="outline"
                          size="sm"
                          icon="file"
                          onClick={() =>
                            navigate('/prds', {
                              state: {
                                prefill: {
                                  sourceType: 'pain_point',
                                  painPointId: pp.id,
                                  title: `Resolve: ${pp.title}`,
                                  prompt: pp.description || pp.recommended_action || '',
                                },
                              },
                            })
                          }
                        >
                          Convert to PRD
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="calendar"
                          onClick={() => navigate('/roadmap', { state: { highlight: pp.title } })}
                          title="View / plan in Roadmap"
                        >
                          Roadmap
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="Feature Demand Opportunities"
                hint="Customer-requested capabilities ranked by priority score"
                actions={
                  clusters.length > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      iconRight="arrowRight"
                      onClick={() => navigate('/prioritization')}
                    >
                      Prioritize ({clusters.length})
                    </Button>
                  )
                }
              />
              <CardBody className="stack stack-sm" style={{ padding: 'var(--sp-3)' }}>
                {topClusters.length === 0 ? (
                  <EmptyState icon="layers" title="No feature clusters yet">
                    Run analysis in Insights to group customer requests into feature ideas.
                  </EmptyState>
                ) : (
                  topClusters.map((cluster, idx) => (
                    <div
                      key={cluster.id || idx}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 'var(--sp-3)',
                        padding: 'var(--sp-2) var(--sp-3)',
                        borderRadius: 'var(--radius)',
                        background: 'var(--bg-subtle)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      <div className="stack stack-xs flex-1">
                        <div className="row" style={{ gap: 'var(--sp-2)' }}>
                          <span className={`rank-pill rank-${idx + 1}`}>#{idx + 1}</span>
                          <Badge tone={DEMAND_TONE[cluster.demand_level] || 'accent'} className="badge-sm">
                            {cluster.demand_level || 'high'} demand
                          </Badge>
                          <strong className="text-sm" style={{ color: 'var(--text)' }}>
                            {cluster.cluster_name}
                          </strong>
                        </div>
                        <span className="text-xs text-muted clamp-1">{cluster.summary}</span>
                        <span className="text-xs text-light row" style={{ gap: 'var(--sp-1)' }}>
                          Score {cluster.priority_score}/100 · {cluster.request_count || 0} requests
                          <Hint label="How feature demand is scored">
                            How often the request appears, how many customers asked, and how
                            negative the surrounding feedback is — 0 to 100.
                          </Hint>
                        </span>
                      </div>
                      <div className="row" style={{ gap: 'var(--sp-1)', flexShrink: 0 }}>
                        <Button
                          variant="primary"
                          size="sm"
                          icon="target"
                          onClick={() => navigate('/prioritization')}
                        >
                          Prioritize
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          icon="file"
                          onClick={() =>
                            navigate('/prds', {
                              state: {
                                prefill: {
                                  sourceType: 'cluster',
                                  clusterId: cluster.id,
                                  title: `Build: ${cluster.cluster_name}`,
                                  prompt: cluster.summary || '',
                                },
                              },
                            })
                          }
                        >
                          PRD
                        </Button>
                      </div>
                    </div>
                  ))
                )}
              </CardBody>
            </Card>
          </div>

          <div className="grid grid-2">
            <Card>
              <CardHeader
                title="What the feedback is about"
                hint="Every item, grouped by the category the classifier assigned."
              />
              <CardBody>
                <CategoryPieChart categoryDistribution={stats?.by_category || {}} totalFeedback={total} />
              </CardBody>
            </Card>

            <Card>
              <CardHeader
                title="How customers feel"
                actions={
                  <Badge tone={SENTIMENT_TONE.positive}>{positivePercent}% positive</Badge>
                }
                hint="Sentiment across every item that carried a tone."
              />
              <CardBody className="stack stack-md">
                <SentimentDonutChart
                  positive={positive}
                  neutral={stats?.by_sentiment?.neutral || 0}
                  negative={stats?.by_sentiment?.negative || 0}
                  healthScore={positivePercent}
                />
                <div className="stack stack-sm">
                  {['positive', 'neutral', 'negative'].map((key) => {
                    const count = stats?.by_sentiment?.[key] || 0;
                    return (
                      <div key={key} className="row" style={{ gap: 'var(--sp-2)' }}>
                        <span
                          className="dot"
                          style={{ color: sentiment[key].line }}
                          aria-hidden="true"
                        />
                        <span className="text-sm" style={{ textTransform: 'capitalize', width: 72 }}>
                          {key}
                        </span>
                        <span className="text-sm text-muted flex-1">{count} items</span>
                        <span className="text-sm text-semibold">{pct(count)}%</span>
                      </div>
                    );
                  })}
                </div>
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Pipeline progress"
              hint="Cleaning normalises the text; categorising assigns a category and sentiment."
              actions={
                cleaned === total && categorized === total ? (
                  <Badge tone="success" icon="checkCircle">
                    Up to date
                  </Badge>
                ) : (
                  <Button variant="outline" size="sm" icon="zap" onClick={() => navigate('/insights')}>
                    Finish processing
                  </Button>
                )
              }
            />
            <CardBody className="stack stack-md">
              <div className="stack stack-sm">
                <div className="row row-between">
                  <span className="text-sm">Cleaned</span>
                  <span className="text-sm text-muted">
                    {cleaned} of {total}
                  </span>
                </div>
                <ProgressBar value={pct(cleaned)} label="Cleaning progress" />
              </div>
              <div className="stack stack-sm">
                <div className="row row-between">
                  <span className="text-sm">Categorised</span>
                  <span className="text-sm text-muted">
                    {categorized} of {total}
                  </span>
                </div>
                <ProgressBar value={pct(categorized)} label="Categorisation progress" />
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="Newest feedback"
              hint={`The ${recentFeedback.length} most recent items in this workspace.`}
              actions={
                recentFeedback.length > 0 && (
                  <Button variant="ghost" size="sm" iconRight="arrowRight" onClick={() => navigate('/feedback')}>
                    View all {total}
                  </Button>
                )
              }
            />

            {recentFeedback.length === 0 ? (
              <EmptyState icon="inbox" title="Nothing here yet">
                Once feedback is imported, the latest items appear in this list.
              </EmptyState>
            ) : (
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Item</th>
                      <th scope="col">Category</th>
                      <th scope="col">Sentiment</th>
                      <th scope="col">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentFeedback.map((item) => (
                      <tr key={item._id || item.title}>
                        <td>
                          <div className="table-primary">
                            <strong className="clamp-2">
                              {item.title || item.content?.slice(0, 90) || 'Untitled feedback'}
                            </strong>
                            {item.title && item.content && (
                              <span className="table-secondary">{item.content}</span>
                            )}
                          </div>
                        </td>
                        <td>
                          {item.category ? (
                            <span
                              className="badge"
                              style={{
                                background: tint(getCategoryColor(item.category)),
                                color: getCategoryColor(item.category),
                                borderColor: tint(getCategoryColor(item.category), 0.22),
                              }}
                            >
                              {item.category.replace(/_/g, ' ')}
                            </span>
                          ) : (
                            <span className="text-light">—</span>
                          )}
                        </td>
                        <td>
                          {item.sentiment ? (
                            <Badge tone={SENTIMENT_TONE[item.sentiment] || 'neutral'}>{item.sentiment}</Badge>
                          ) : (
                            <span className="text-light">—</span>
                          )}
                        </td>
                        <td>
                          <div className="stack stack-sm">
                            <span className="text-sm">{(item.source || 'review').replace(/_/g, ' ')}</span>
                            <span className="text-xs text-muted">
                              {item.customer_name || 'Anonymous'}
                              {item.rating ? ` · ${stars(item.rating)}` : ''}
                            </span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
