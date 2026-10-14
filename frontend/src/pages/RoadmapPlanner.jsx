import { useCallback, useEffect, useMemo, useState } from 'react';
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
  Hint,
  Input,
  Menu,
  PageHeader,
  ProgressBar,
  Section,
  SkeletonCardGrid,
  Toolbar,
  ToolbarField,
} from '../components/ui';

/**
 * How far along a release window is, in words.
 *
 * A plan that says "Oct 7" tells a reader nothing on its own; the useful fact is
 * that it is happening now and how much of it is left.
 */
function releaseTiming(start, end) {
  const day = 86400000;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const from = new Date(start);
  const to = new Date(end);
  if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return { note: '', phase: '' };
  if (today < from) return { note: `starts in ${Math.round((from - today) / day)} days`, phase: 'upcoming' };
  if (today > to) return { note: `ended ${Math.round((today - to) / day)} days ago`, phase: 'past' };
  return { note: `${Math.round((to - today) / day)} days left`, phase: 'live' };
}

/**
 * One initiative, as it appears inside a milestone.
 *
 * A card carries only what a reader needs to compare it with its neighbours:
 * the name, how committed it is, and how much work it is. The four scores that
 * used to sit on the card face now live behind “Why here”, together with the
 * rationale — available, but not competing with the title.
 */
function InitiativeCard({ item, releases, currentIndex, onMove, onDragStart, onDragEnd }) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="roadmap-item"
      draggable={Boolean(onDragStart)}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <div className="roadmap-item-head">
        {onDragStart && (
          <span className="roadmap-item-handle" aria-hidden="true">
            <Icon name="menu" size={14} />
          </span>
        )}
        <strong>{item.name}</strong>
        <Badge tone={MOSCOW_TONES[item.moscow] || 'neutral'}>
          {MOSCOW_LABELS[item.moscow] || item.moscow}
        </Badge>
      </div>

      <div className="roadmap-item-meta">
        <span className="row" style={{ gap: 'var(--sp-1)' }}>
          Effort {item.effort}
          <Hint label="What effort means">
            Person-months of work, carried over from Prioritization.
          </Hint>
        </span>
      </div>

      <div className="roadmap-item-actions">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <Icon name={open ? 'chevronUp' : 'chevronDown'} size={14} />
          Why here
        </button>

        {onMove && (
          <Menu
            label={`Move ${item.name}`}
            items={releases.map((target, index) => ({
              label: index === currentIndex ? `${target.name} (current)` : `Move to ${target.name}`,
              icon: index === currentIndex ? 'check' : 'arrowRight',
              disabled: index === currentIndex,
              onSelect: () => onMove(item, index),
            }))}
          />
        )}
      </div>

      {open && (
        <div className="stack stack-sm roadmap-item-detail">
          <div className="roadmap-item-meta">
            <span className="row" style={{ gap: 'var(--sp-1)' }}>
              RICE {Math.round(item.rice_score).toLocaleString()}
              <Hint label="What RICE means">
                Reach × impact × confidence ÷ effort, carried over from Prioritization.
              </Hint>
            </span>
            <span>Weighted {item.weighted_score}</span>
            <span>{item.feedback_count} customer records</span>
            <span>{CATEGORY_LABELS[item.category] || item.category}</span>
          </div>
          {item.rationale && <p className="text-sm">{item.rationale}</p>}
          {item.description && <p className="text-muted text-sm">{item.description}</p>}
        </div>
      )}
    </div>
  );
}

/**
 * Roadmap — turn the prioritised backlog into a sequenced plan.
 *
 * Everything on this page comes from the backend plan: the ordering rule, the
 * release it lands in, the milestones and the exit criteria are all computed from
 * the workspace's own prioritization and analysis data. The page only presents it
 * and lets a PM move one initiative between releases.
 *
 * Nothing here is estimated. Where a milestone states an outcome, it is labelled
 * "Measured:" against "Proposed:" — the same convention the PRD uses, so a reader
 * can always tell which half of a sentence is data and which half is a target.
 */

const CONFIDENCE_TONES = { high: 'success', medium: 'warning', low: 'danger' };
const HORIZON_TONES = { now: 'accent', next: 'neutral', later: 'neutral' };
const HORIZON_LABELS = { now: 'Now', next: 'Next', later: 'Later', backlog: 'Backlog' };

const CATEGORY_LABELS = {
  general_feedback: 'General',
  bug_report: 'Defect',
  bug_fix: 'Defect',
  performance: 'Performance',
  performance_issue: 'Performance',
  security: 'Security',
  feature_request: 'Feature',
};

const MOSCOW_LABELS = {
  must_have: 'Must have',
  should_have: 'Should have',
  could_have: 'Could have',
  wont_have: 'Won’t have',
};

const MOSCOW_TONES = {
  must_have: 'danger',
  should_have: 'accent',
  could_have: 'neutral',
  wont_have: 'neutral',
};

const formatDate = (value) => {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
};

export default function RoadmapPlanner() {
  const { begin } = useBusy();
  const navigate = useNavigate();
  const { activeId: workspaceId, activeWorkspace, ready } = useWorkspaces();

  const [roadmap, setRoadmap] = useState(() => (workspaceId ? api.getCached(`/roadmap/${workspaceId}`) : null));
  const [loading, setLoading] = useState(() => !workspaceId || !api.getCached(`/roadmap/${workspaceId}`));
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const [horizonWeeks, setHorizonWeeks] = useState('12');
  const [velocity, setVelocity] = useState('8');
  const [focus, setFocus] = useState('');
  const [openMilestone, setOpenMilestone] = useState('');
  const [showInputs, setShowInputs] = useState(false);
  // Which release lanes have been expanded past their first three items, and
  // which single item is being dragged between lanes.
  const [expandedLanes, setExpandedLanes] = useState({});
  const [dragItem, setDragItem] = useState(null);

  const loadRoadmap = useCallback(async (id) => {
    if (!id) return;
    setError('');
    if (!api.getCached(`/roadmap/${id}`)) {
      setLoading(true);
    }
    try {
      const { data } = await api.get(`/roadmap/${id}`);
      setRoadmap(data);
      setOpenMilestone('');
    } catch (err) {
      // A workspace that has never been planned answers 404 — that is an empty
      // state, not a failure, and it must not read like one.
      if (err?.response?.status === 404) {
        setRoadmap(null);
      } else {
        setError('Could not load the roadmap for this workspace.');
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (workspaceId) loadRoadmap(workspaceId);
  }, [workspaceId, loadRoadmap]);

  const generate = async () => {
    if (!workspaceId) return;
    setGenerating(true);
    setError('');
    setNotice('');
    const done = begin('Planning the roadmap…');
    try {
      const { data } = await api.post('/roadmap/generate', {
        workspace_id: workspaceId,
        horizon_weeks: Number(horizonWeeks) || 12,
        velocity: Number(velocity) || 8,
        focus: focus.trim() || null,
      });
      setRoadmap(data);
      setOpenMilestone('');
      setNotice(
        data?.items?.length
          ? `Sequenced ${data.items.length} initiative(s) across ${data.releases.length} release window(s).`
          : 'There is nothing to sequence yet — seed the backlog from the Prioritization page first.'
      );
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not generate the roadmap.');
    } finally {
      setGenerating(false);
      done();
    }
  };

  const moveItem = async (item, targetIndex) => {
    if (!workspaceId || !roadmap) return;
    const done = begin('Rescheduling…');
    try {
      const { data } = await api.patch(`/roadmap/${workspaceId}/items/${item.id}`, {
        target_release_index: Number(targetIndex),
      });
      setRoadmap(data);
      setNotice(`Moved “${item.name}” into ${data.releases[Number(targetIndex)]?.name || 'another release'}.`);
    } catch (err) {
      setError(err?.response?.data?.detail || 'Could not move that initiative.');
    } finally {
      done();
    }
  };

  const exportMarkdown = async () => {
    if (!workspaceId) return;
    try {
      const { data } = await api.get(`/roadmap/${workspaceId}/export`);
      const blob = new Blob([typeof data === 'string' ? data : JSON.stringify(data, null, 2)], {
        type: 'text/markdown',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `roadmap-${roadmap?.workspace_name || 'workspace'}.md`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setNotice('Roadmap exported as Markdown.');
    } catch {
      setError('Could not export the roadmap.');
    }
  };

  const itemsByRelease = useMemo(() => {
    const grouped = {};
    (roadmap?.items || []).forEach((item) => {
      const key = item.release || 'Backlog';
      grouped[key] = grouped[key] || [];
      grouped[key].push(item);
    });
    return grouped;
  }, [roadmap]);

  const summary = useMemo(() => {
    if (!roadmap) return null;
    return {
      scheduled: roadmap.evidence?.items_planned ?? 0,
      backlog: roadmap.evidence?.items_deferred ?? 0,
      records: roadmap.evidence?.planned_feedback_records ?? 0,
      mustHave: roadmap.evidence?.must_have_coverage || '0 of 0',
    };
  }, [roadmap]);

  // The four stat cards this page used to open with said the same thing as one
  // sentence, in four times the space. One line, read in a glance.
  const summaryLine = useMemo(() => {
    if (!roadmap || !summary) return '';
    const match = String(summary.mustHave || '').match(/(\d+)\s*(?:of|\/)\s*(\d+)/i);
    const covered = match ? parseInt(match[1], 10) : null;
    const total = match ? parseInt(match[2], 10) : null;
    let mustLine = '';
    if (covered != null && total != null) {
      mustLine = covered === total ? `all ${covered} must-haves scheduled` : `${covered} of ${total} must-haves scheduled`;
    } else if (summary.mustHave) {
      mustLine = String(summary.mustHave);
    }
    const releaseCount = (roadmap.releases || []).length;
    return [
      `${releaseCount} release${releaseCount === 1 ? '' : 's'}`,
      `${summary.scheduled} initiative${summary.scheduled === 1 ? '' : 's'}`,
      mustLine,
    ]
      .filter(Boolean)
      .join(' · ');
  }, [roadmap, summary]);

  return (
    <div className="page-container stack stack-lg">
      <PageHeader
        icon="calendar"
        title="Roadmap"
        trail="roadmap"
        description={
          activeWorkspace
            ? `A sequenced plan for ${activeWorkspace.name}, built from its prioritised customer evidence.`
            : 'Sequence the prioritised backlog into releases and recommended milestones.'
        }
        actions={
          roadmap ? (
            <>
              <Button variant="outline" icon="download" onClick={exportMarkdown}>
                Export
              </Button>
              <Button icon="sparkle" onClick={generate} disabled={!ready || !workspaceId || generating} loading={generating}>
                Re-plan
              </Button>
            </>
          ) : null
        }
      />

      {error && <Alert variant="danger" title="Roadmap unavailable">{error}</Alert>}
      {notice && <Alert variant="success" title="Plan updated">{notice}</Alert>}

      {/* The parameters only deserve a card of their own before there is a plan;
          afterwards they are one link beside the summary they produced. */}
      {!roadmap && (
        <Card>
          <CardHeader title="Planning parameters" hint="Capacity in effort units per 4-week release" />
          <CardBody>
            <Toolbar
              left={
                <>
                  <ToolbarField label="Horizon (weeks)" htmlFor="roadmap-horizon">
                    <Input
                      id="roadmap-horizon"
                      type="number"
                      min="4"
                      max="52"
                      step="4"
                      value={horizonWeeks}
                      onChange={(event) => setHorizonWeeks(event.target.value)}
                    />
                  </ToolbarField>
                  <ToolbarField label="Capacity per release" htmlFor="roadmap-velocity">
                    <Input
                      id="roadmap-velocity"
                      type="number"
                      min="0.5"
                      max="100"
                      step="0.5"
                      value={velocity}
                      onChange={(event) => setVelocity(event.target.value)}
                    />
                  </ToolbarField>
                  <ToolbarField label="Strategic focus (optional)" htmlFor="roadmap-focus">
                    <Input
                      id="roadmap-focus"
                      type="text"
                      placeholder="e.g. retention before growth"
                      value={focus}
                      onChange={(event) => setFocus(event.target.value)}
                    />
                  </ToolbarField>
                </>
              }
            />
          </CardBody>
        </Card>
      )}

      {loading && <SkeletonCardGrid count={3} />}

      {!loading && !roadmap && (
        <EmptyState
          icon="calendar"
          title="No roadmap yet"
          actions={
            <Button
              icon="sparkle"
              onClick={generate}
              disabled={generating || !ready || !workspaceId}
              loading={generating}
            >
              {generating ? 'Generating plan…' : 'Generate plan'}
            </Button>
          }
        >
          This workspace has not been planned yet. Adjust your planning inputs above and click Generate plan to sequence the prioritised backlog into release windows and milestones based on real customer feedback.
        </EmptyState>
      )}

      {!loading && roadmap && (
        <>
          <Card>
            <CardHeader
              title={summaryLine}
              hint={`${summary.records.toLocaleString()} customer records behind these decisions.`}
              actions={
                <Button
                  variant="ghost"
                  size="sm"
                  icon={showInputs ? 'chevronUp' : 'sliders'}
                  onClick={() => setShowInputs((v) => !v)}
                >
                  {showInputs ? 'Hide parameters' : 'Adjust parameters'}
                </Button>
              }
            />
            <CardBody className="stack stack-md">
              <p className="prose text-sm" style={{ margin: 0 }}>{roadmap.strategy}</p>
              <div className="meta-line">
                Planned {formatDate(roadmap.generated_at)} · {roadmap.horizon_weeks}-week horizon ·{' '}
                {roadmap.velocity} effort per release
                <Hint label="What wrote this plan">
                  {roadmap.ai_generated
                    ? `Narrative written by ${roadmap.ai_model}; every release, ordering and date computed from this workspace's prioritisation.`
                    : 'Sequenced deterministically from this workspace’s prioritisation — no model involved.'}
                </Hint>
              </div>

              {showInputs && (
                <Toolbar
                  left={
                    <>
                      <ToolbarField label="Horizon (weeks)" htmlFor="roadmap-horizon">
                        <Input
                          id="roadmap-horizon"
                          type="number"
                          min="4"
                          max="52"
                          step="4"
                          value={horizonWeeks}
                          onChange={(event) => setHorizonWeeks(event.target.value)}
                        />
                      </ToolbarField>
                      <ToolbarField label="Capacity per release" htmlFor="roadmap-velocity">
                        <Input
                          id="roadmap-velocity"
                          type="number"
                          min="0.5"
                          max="100"
                          step="0.5"
                          value={velocity}
                          onChange={(event) => setVelocity(event.target.value)}
                        />
                      </ToolbarField>
                      <ToolbarField label="Strategic focus (optional)" htmlFor="roadmap-focus">
                        <Input
                          id="roadmap-focus"
                          type="text"
                          placeholder="e.g. retention before growth"
                          value={focus}
                          onChange={(event) => setFocus(event.target.value)}
                        />
                      </ToolbarField>
                    </>
                  }
                />
              )}
            </CardBody>
          </Card>

          <Section
            title="Release plan"
            hint="Drag an initiative between releases, or use its menu — the milestones, capacity totals and exit criteria recompute around it."
          >
            <div className="roadmap-lanes">
              {(roadmap.releases || []).map((release, releaseIndex) => {
                const releaseItems = itemsByRelease[release.name] || [];
                const milestones = (roadmap.milestones || []).filter(
                  (milestone) => milestone.release === release.name
                );
                // Each initiative is drawn once, inside the milestone that owns
                // it. Anything the planner left ungrouped falls into one lane-level
                // list rather than being repeated next to its group.
                const claimed = new Set();
                const milestoneItems = milestones.map((milestone) => {
                  const owned = releaseItems.filter((item) =>
                    item.milestone_id
                      ? item.milestone_id === milestone.id
                      : (milestone.item_ids || []).includes(item.id)
                  );
                  owned.forEach((item) => claimed.add(item.id));
                  return { milestone, items: owned };
                });
                const ungrouped = releaseItems.filter((item) => !claimed.has(item.id));
                const overCommitted = release.effort_total > release.capacity;
                const timing = releaseTiming(release.start_date, release.end_date);
                const expanded = Boolean(expandedLanes[release.name]);
                const ITEM_LIMIT = 3;
                const shownCount =
                  milestoneItems.reduce(
                    (total, group) => total + (expanded ? group.items.length : Math.min(group.items.length, ITEM_LIMIT)),
                    0
                  ) + (expanded ? ungrouped.length : Math.min(ungrouped.length, ITEM_LIMIT));
                return (
                  <Card
                    key={release.name}
                    className={`roadmap-lane${dragItem ? ' is-drop-target' : ''}`}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (dragItem) moveItem(dragItem, releaseIndex);
                      setDragItem(null);
                    }}
                  >
                    <CardHeader
                      title={release.name}
                      hint={`${formatDate(release.start_date)} → ${formatDate(release.end_date)}${
                        timing.note ? ` · ${timing.note}` : ''
                      }`}
                      actions={
                        <Badge tone={timing.phase === 'live' ? 'accent' : HORIZON_TONES[release.horizon] || 'neutral'}>
                          {timing.phase === 'live'
                            ? 'Now'
                            : HORIZON_LABELS[release.horizon] || release.horizon}
                        </Badge>
                      }
                    />
                    <CardBody className="stack stack-md">
                      <div className="roadmap-lane-meta">
                        <span className="roadmap-lane-effort">
                          {release.effort_total} of {release.capacity} effort · {release.item_count} item
                          {release.item_count === 1 ? '' : 's'}
                          <Hint label="What capacity means">
                            Effort units the team can take on in this window. Over capacity means the
                            release will not fit as planned.
                          </Hint>
                        </span>
                        {overCommitted && <Badge tone="warning">Over capacity</Badge>}
                      </div>
                      <ProgressBar
                        value={
                          release.capacity > 0
                            ? Math.round((release.effort_total / release.capacity) * 100)
                            : 0
                        }
                        label={`${release.name} capacity used`}
                      />

                      {milestoneItems.map(({ milestone, items: groupItems }) => {
                        const isOpen = openMilestone === milestone.id;
                        const visible = expanded ? groupItems : groupItems.slice(0, ITEM_LIMIT);
                        return (
                          <div key={milestone.id} className="roadmap-milestone">
                            <button
                              type="button"
                              className="roadmap-milestone-head"
                              aria-expanded={isOpen}
                              onClick={() =>
                                setOpenMilestone((current) => (current === milestone.id ? '' : milestone.id))
                              }
                            >
                              <Icon name={isOpen ? 'chevronDown' : 'chevronRight'} size={14} />
                              <span>{milestone.name}</span>
                              <Badge tone={CONFIDENCE_TONES[milestone.confidence] || 'neutral'}>
                                {milestone.confidence} evidence
                              </Badge>
                            </button>

                            <p className="roadmap-milestone-objective">{milestone.objective}</p>
                            <p className="text-muted text-xs">
                              {groupItems.length || milestone.item_count} initiative
                              {(groupItems.length || milestone.item_count) === 1 ? '' : 's'} ·{' '}
                              {milestone.effort_total} effort · {milestone.feedback_count} customer records
                            </p>

                            {isOpen && (
                              <div className="stack stack-sm roadmap-milestone-detail">
                                <p className="text-sm">{milestone.rationale}</p>

                                <h4 className="section-title">Exit criteria</h4>
                                <ul className="roadmap-list">
                                  {(milestone.exit_criteria || []).map((criterion) => (
                                    <li key={criterion}>{criterion}</li>
                                  ))}
                                </ul>

                                <h4 className="section-title">Success metrics</h4>
                                <div className="table-responsive">
                                  <table className="table">
                                    <thead>
                                      <tr>
                                        <th scope="col">Metric</th>
                                        <th scope="col">Baseline</th>
                                        <th scope="col">Target</th>
                                        <th scope="col">Tracking</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {(milestone.success_metrics || []).map((metric) => (
                                        <tr key={metric.metric}>
                                          <td>{metric.metric}</td>
                                          <td>{metric.baseline}</td>
                                          <td>{metric.target}</td>
                                          <td className="text-muted text-sm">{metric.tracking_mechanism}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              </div>
                            )}

                            {/* The milestone's own initiatives, nested under it — not
                                repeated a second time further down the lane. */}
                            {visible.length > 0 && (
                              <div className="roadmap-milestone-items">
                                {visible.map((item) => (
                                  <InitiativeCard
                                    key={item.id}
                                    item={item}
                                    releases={roadmap.releases || []}
                                    currentIndex={releaseIndex}
                                    onMove={moveItem}
                                    onDragStart={() => setDragItem(item)}
                                    onDragEnd={() => setDragItem(null)}
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}

                      {ungrouped.length > 0 && (
                        <div className="roadmap-milestone">
                          <p className="roadmap-milestone-objective">Also in this release</p>
                          <p className="text-muted text-xs">
                            Sequenced into the window, not yet bundled into a milestone.
                          </p>
                          <div className="roadmap-milestone-items">
                            {(expanded ? ungrouped : ungrouped.slice(0, ITEM_LIMIT)).map((item) => (
                              <InitiativeCard
                                key={item.id}
                                item={item}
                                releases={roadmap.releases || []}
                                currentIndex={releaseIndex}
                                onMove={moveItem}
                                onDragStart={() => setDragItem(item)}
                                onDragEnd={() => setDragItem(null)}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      {!releaseItems.length && (
                        <p className="text-muted text-sm">
                          No initiative fits this window at the current capacity. Drag one here from
                          another release.
                        </p>
                      )}

                      {releaseItems.length > shownCount && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="chevronDown"
                          onClick={() => setExpandedLanes((current) => ({ ...current, [release.name]: true }))}
                        >
                          Show all {releaseItems.length} initiatives
                        </Button>
                      )}
                      {expanded && releaseItems.length > ITEM_LIMIT && (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon="chevronUp"
                          onClick={() => setExpandedLanes((current) => ({ ...current, [release.name]: false }))}
                        >
                          Show fewer
                        </Button>
                      )}
                    </CardBody>
                  </Card>
                );
              })}
            </div>
          </Section>

          {(roadmap.deferred || []).length > 0 && (
            <Section title="Backlog beyond the horizon" hint={roadmap.deferred_reason}>
              <Card>
                <CardBody className="stack stack-sm">
                  {roadmap.deferred.map((item) => (
                    <InitiativeCard
                      key={item.id}
                      item={item}
                      releases={roadmap.releases || []}
                      currentIndex={null}
                      onMove={moveItem}
                    />
                  ))}
                </CardBody>
              </Card>
            </Section>
          )}

          <Section title="Next step" hint="The plan is only as good as the documents behind it.">
            <Card>
              <CardBody className="row row-between row-wrap">
                <p className="text-sm text-muted" style={{ margin: 0, maxWidth: '60ch' }}>
                  Turn the first milestone into a written product requirement, then break it into
                  stories the team can pick up.
                </p>
                <div className="row">
                  <Menu
                    label="Other next steps"
                    items={[
                      {
                        label: 'Break into user stories',
                        icon: 'layers',
                        onSelect: () => navigate('/user-stories'),
                      },
                      { label: 'Report on the plan', icon: 'checkCircle', onSelect: () => navigate('/reports') },
                    ]}
                  />
                  <Button variant="primary" icon="clipboard" onClick={() => navigate('/prds')}>
                    Write the PRD
                  </Button>
                </div>
              </CardBody>
            </Card>
          </Section>
        </>
      )}
    </div>
  );
}
