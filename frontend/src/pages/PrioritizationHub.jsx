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
  IconButton,
  Input,
  Modal,
  PageHeader,
  Select,
  SkeletonTable,
  Stat,
  StatGrid,
  Tabs,
  Textarea,
  Toolbar,
} from '../components/ui';

const FRAMEWORKS = [
  { value: 'rice', label: 'RICE', icon: 'barChart' },
  { value: 'matrix', label: 'Value vs effort', icon: 'target' },
  { value: 'moscow', label: 'MoSCoW', icon: 'clipboard' },
  { value: 'weighted', label: 'Weighted scoring', icon: 'layers' },
];

const QUADRANTS = {
  quick_win: { label: 'Quick wins', desc: 'High value, low effort', tone: 'success' },
  major_project: { label: 'Major projects', desc: 'High value, high effort', tone: 'accent' },
  fill_in: { label: 'Fill-ins', desc: 'Low value, low effort', tone: 'warning' },
  thankless_task: { label: 'Thankless tasks', desc: 'Low value, high effort', tone: 'danger' },
};

const MOSCOW_COLUMNS = [
  { id: 'must_have', label: 'Must have', note: 'Non-negotiable for this release' },
  { id: 'should_have', label: 'Should have', note: 'Important, but not blocking' },
  { id: 'could_have', label: 'Could have', note: 'Worth doing if capacity allows' },
  { id: 'wont_have', label: 'Won’t have', note: 'Deliberately out of scope' },
];

const WEIGHT_FIELDS = [
  { key: 'customer_demand_weight', label: 'Customer demand' },
  { key: 'business_impact_weight', label: 'Business impact' },
  { key: 'feasibility_weight', label: 'Technical feasibility' },
  { key: 'risk_mitigation_weight', label: 'Risk mitigation' },
];

const CATEGORY_OPTIONS = [
  { value: 'feature_request', label: 'Feature request' },
  { value: 'bug_fix', label: 'Bug fix / stability' },
  { value: 'performance', label: 'Performance' },
  { value: 'security', label: 'Security & compliance' },
];

const IMPACT_OPTIONS = [
  { value: '0.25', label: '0.25 — minimal' },
  { value: '0.5', label: '0.5 — low' },
  { value: '1', label: '1.0 — medium' },
  { value: '2', label: '2.0 — high' },
  { value: '3', label: '3.0 — massive' },
];

/**
 * Prioritization — decide what to build next.
 *
 * Four frameworks over the same initiative list, so they share one toolbar,
 * one tab pattern and one table. The page's one filled button is the next step
 * in the flow — the roadmap; adding, seeding and calibrating are the working
 * strip below it.
 */
export default function PrioritizationHub() {
  const { begin } = useBusy();
  const navigate = useNavigate();

  const { activeId: workspaceId, ready } = useWorkspaces();
  const [items, setItems] = useState(() => (workspaceId ? api.getCached(`/prioritization/workspace/${workspaceId}`) || [] : []));
  const [weights, setWeights] = useState(() => {
    const cached = workspaceId ? api.getCached(`/prioritization/workspace/${workspaceId}/weights`) : null;
    return {
      customer_demand_weight: 0.35,
      business_impact_weight: 0.3,
      feasibility_weight: 0.2,
      risk_mitigation_weight: 0.15,
      ...(cached || {}),
    };
  });

  const [loading, setLoading] = useState(() => !workspaceId || !api.getCached(`/prioritization/workspace/${workspaceId}`));
  const [busyAction, setBusyAction] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [tab, setTab] = useState('rice');
  const [selected, setSelected] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);

  const [showAdd, setShowAdd] = useState(false);
  const [draft, setDraft] = useState({
    name: '',
    description: '',
    category: 'feature_request',
    reach: '1000',
    impact: '2',
    effort: '2',
    moscow: 'should_have',
  });

  const loadData = useCallback(async (id) => {
    if (!id) return;
    if (!api.getCached(`/prioritization/workspace/${id}`)) {
      setLoading(true);
    }
    setError('');
    try {
      const [itemsResult, weightsResult] = await Promise.all([
        api.get(`/prioritization/workspace/${id}`),
        api.get(`/prioritization/workspace/${id}/weights`),
      ]);
      setItems(itemsResult.data);
      if (weightsResult.data) {
        setWeights((prev) => ({ ...prev, ...weightsResult.data }));
      }
    } catch {
      setError('Could not load the prioritisation data for this workspace.');
    } finally {
      setLoading(false);
    }
  }, []);

  // The initiative list follows the shared selection, so a switch anywhere in
  // the app reloads this page too.
  useEffect(() => {
    if (workspaceId) loadData(workspaceId);
  }, [workspaceId, loadData]);

  useEffect(() => {
    if (ready && !workspaceId) setLoading(false);
  }, [ready, workspaceId]);

  const runWorkspaceAction = async (key, path, label, message) => {
    const done = begin(label);
    setBusyAction(key);
    setError('');
    setNotice('');
    try {
      const { data } = await api.post(path);
      setItems(data);
      setNotice(message);
    } catch {
      setError(`${label} failed. Nothing was changed.`);
    } finally {
      setBusyAction('');
      done();
    }
  };

  const updateScore = async (itemId, group, field, value) => {
    const previous = items;
    const next = items.map((item) => {
      if (item.id !== itemId) return item;
      const copy = { ...item };
      if (group === 'rice') {
        copy.rice = { ...copy.rice, [field]: parseFloat(value) };
        const effort = Math.max(0.5, copy.rice.effort || 1);
        copy.rice.score = Math.round(
          ((copy.rice.reach || 0) * (copy.rice.impact || 0) * (copy.rice.confidence || 0.8)) / effort
        );
      } else if (group === 'value_vs_effort') {
        copy.value_vs_effort = { ...copy.value_vs_effort, [field]: parseFloat(value) };
        const v = copy.value_vs_effort.value;
        const e = copy.value_vs_effort.effort;
        copy.value_vs_effort.quadrant =
          v >= 5 ? (e < 5 ? 'quick_win' : 'major_project') : e < 5 ? 'fill_in' : 'thankless_task';
      } else if (group === 'moscow') {
        copy.moscow = value;
      }
      return copy;
    });

    setItems(next);

    try {
      const item = next.find((i) => i.id === itemId);
      await api.put(`/prioritization/item/${itemId}`, {
        reach: item.rice.reach,
        impact: item.rice.impact,
        confidence: item.rice.confidence,
        effort: item.rice.effort,
        value: item.value_vs_effort.value,
        effort_score: item.value_vs_effort.effort,
        moscow: item.moscow,
      });
      setNotice('');
    } catch {
      setItems(previous);
      setError('That change could not be saved, so it has been rolled back.');
    }
  };

  const saveWeights = async () => {
    const done = begin('Re-ranking with new weights');
    setBusyAction('weights');
    try {
      await api.post(`/prioritization/workspace/${workspaceId}/weights`, weights);
      await loadData(workspaceId);
      setNotice('Weights saved and every initiative re-ranked.');
    } catch {
      setError('Could not save those weights.');
    } finally {
      setBusyAction('');
      done();
    }
  };

  const addItem = async () => {
    if (!workspaceId || !draft.name.trim()) return;
    setBusyAction('add');
    try {
      await api.post('/prioritization/item', {
        workspace_id: workspaceId,
        name: draft.name.trim(),
        description: draft.description,
        category: draft.category,
        reach: parseFloat(draft.reach),
        impact: parseFloat(draft.impact),
        confidence: 0.8,
        effort: parseFloat(draft.effort),
        value: 7.5,
        moscow: draft.moscow,
      });
      setShowAdd(false);
      setDraft({ ...draft, name: '', description: '' });
      await loadData(workspaceId);
    } catch {
      setError('Could not add that initiative.');
    } finally {
      setBusyAction('');
    }
  };

  const confirmDelete = async () => {
    const item = pendingDelete;
    setPendingDelete(null);
    if (!item) return;
    const previous = items;
    setItems((prev) => prev.filter((i) => i.id !== item.id));
    try {
      await api.delete(`/prioritization/item/${item.id}`);
    } catch {
      setItems(previous);
      setError('Could not delete that initiative.');
    }
  };

  const riceRanked = [...items].sort((a, b) => (b.rice?.score || 0) - (a.rice?.score || 0));
  const quickWins = items.filter((i) => i.value_vs_effort?.quadrant === 'quick_win').length;
  const mustHaves = items.filter((i) => (i.moscow || 'should_have') === 'must_have').length;
  const topScore = riceRanked[0]?.rice?.score || 0;

  const weightedRanked = items
    .map((item) => {
      const totalWeight =
        weights.customer_demand_weight +
          weights.business_impact_weight +
          weights.feasibility_weight +
          weights.risk_mitigation_weight || 1;
      const score = Math.round(
        ((item.weighted?.customer_demand_score || 70) * weights.customer_demand_weight +
          (item.weighted?.business_impact_score || 70) * weights.business_impact_weight +
          (item.weighted?.feasibility_score || 70) * weights.feasibility_weight +
          (item.weighted?.risk_mitigation_score || 70) * weights.risk_mitigation_weight) /
          totalWeight
      );
      return { ...item, weightedTotal: score };
    })
    .sort((a, b) => b.weightedTotal - a.weightedTotal);

  return (
    <div className="page-container">
      <PageHeader
        icon="scale"
        title="Prioritization"
        trail="prioritized"
        description="Rank one initiative list four ways — RICE, value against effort, MoSCoW or your own weights."
        actions={
          <Button variant="primary" icon="arrowRight" disabled={!items.length} onClick={() => navigate('/roadmap')}>
            Plan releases
          </Button>
        }
      />

      {notice && <Alert variant="success">{notice}</Alert>}
      {error && <Alert variant="error">{error}</Alert>}

      <Toolbar
        left={
          <>
            <Button variant="outline" icon="plus" disabled={!workspaceId} onClick={() => setShowAdd(true)}>
              Add initiative
            </Button>
            <Button
              variant="outline"
              icon="refresh"
              disabled={!workspaceId}
              loading={busyAction === 'seed'}
              onClick={() =>
                runWorkspaceAction(
                  'seed',
                  `/prioritization/workspace/${workspaceId}/auto-seed`,
                  'Seeding from feedback',
                  'Initiatives seeded from feature clusters and pain points.'
                )
              }
            >
              Seed from feedback
            </Button>
            <Button
              variant="outline"
              icon="sparkle"
              disabled={!workspaceId}
              loading={busyAction === 'evaluate'}
              onClick={() =>
                runWorkspaceAction(
                  'evaluate',
                  `/prioritization/workspace/${workspaceId}/ai-evaluate`,
                  'Calibrating scores',
                  'Scores recalibrated from the feedback evidence.'
                )
              }
            >
              Calibrate scores
            </Button>
          </>
        }
        right={<span className="text-xs text-muted">{items.length} initiatives</span>}
      />

      {loading ? (
        <Card flush>
          <SkeletonTable rows={6} columns={7} />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon="scale"
            title="No initiatives to rank yet"
            actions={
              <>
                <Button
                  variant="outline"
                  icon="refresh"
                  onClick={() =>
                    runWorkspaceAction(
                      'seed',
                      `/prioritization/workspace/${workspaceId}/auto-seed`,
                      'Seeding from feedback',
                      'Initiatives seeded from feature clusters and pain points.'
                    )
                  }
                >
                  Seed from feedback
                </Button>
                <Button variant="primary" icon="plus" onClick={() => setShowAdd(true)}>
                  Add one manually
                </Button>
              </>
            }
          >
            Seeding pulls your feature clusters and pain points in with estimated RICE inputs, so you
            start from evidence rather than a blank list.
          </EmptyState>
        </Card>
      ) : (
        <>
          <StatGrid min={170}>
            <Stat label="Initiatives" value={items.length} icon="scale" featured />
            <Stat label="Top RICE score" value={Math.round(topScore).toLocaleString()} hint="Highest of the set" />
            <Stat label="Quick wins" value={quickWins} hint="High value, low effort" />
            <Stat label="Must have" value={mustHaves} hint="Committed for this release" />
          </StatGrid>

          <Tabs tabs={FRAMEWORKS} value={tab} onChange={setTab} label="Prioritization framework" />

          {tab === 'rice' && (
            <Card flush>
              <CardHeader
                title="RICE scoring"
                hint="Score = (Reach × Impact × Confidence) ÷ Effort. Edit any input and the row re-ranks."
              />
              <div className="table-responsive">
                <table className="table">
                  <thead>
                    <tr>
                      <th scope="col">Rank</th>
                      <th scope="col">Initiative</th>
                      <th scope="col">Reach /mo</th>
                      <th scope="col">Impact</th>
                      <th scope="col">Confidence</th>
                      <th scope="col">Effort</th>
                      <th scope="col">Score</th>
                      <th scope="col" className="tight">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {riceRanked.map((item, index) => (
                      <tr key={item.id}>
                        <td>
                          <span className="rank-badge">{index + 1}</span>
                        </td>
                        <td>
                          <div className="prio-name-box">
                            <span className="prio-name">{item.name}</span>
                            {item.description && <span className="prio-desc">{item.description}</span>}
                            {item.ai_rationale && (
                              <span className="prio-ai-note">
                                <Icon name="bulb" size={13} /> {item.ai_rationale}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <input
                            type="number"
                            className="table-input"
                            aria-label={`Reach for ${item.name}`}
                            value={item.rice?.reach || 500}
                            step="50"
                            min="10"
                            onChange={(e) => updateScore(item.id, 'rice', 'reach', e.target.value)}
                          />
                        </td>
                        <td>
                          <select
                            className="table-select"
                            aria-label={`Impact for ${item.name}`}
                            value={item.rice?.impact || 1}
                            onChange={(e) => updateScore(item.id, 'rice', 'impact', e.target.value)}
                          >
                            {IMPACT_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            className="table-select"
                            aria-label={`Confidence for ${item.name}`}
                            value={item.rice?.confidence || 0.8}
                            onChange={(e) => updateScore(item.id, 'rice', 'confidence', e.target.value)}
                          >
                            <option value="0.5">50% — low</option>
                            <option value="0.7">70% — fair</option>
                            <option value="0.8">80% — medium</option>
                            <option value="0.9">90% — high</option>
                            <option value="1">100% — certain</option>
                          </select>
                        </td>
                        <td>
                          <input
                            type="number"
                            className="table-input"
                            aria-label={`Effort for ${item.name}`}
                            value={item.rice?.effort || 2}
                            step="0.5"
                            min="0.5"
                            max="10"
                            onChange={(e) => updateScore(item.id, 'rice', 'effort', e.target.value)}
                          />
                        </td>
                        <td>
                          <span className="rice-score-pill">
                            {Math.round(item.rice?.score || 0).toLocaleString()}
                          </span>
                        </td>
                        <td>
                          <IconButton
                            icon="trash"
                            variant="danger"
                            size="sm"
                            label={`Delete ${item.name}`}
                            onClick={() => setPendingDelete(item)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}

          {tab === 'matrix' && (
            <Card>
              <CardHeader
                title="Value against effort"
                hint="Select an initiative to adjust its two scores; the quadrant updates live."
              />
              <CardBody>
                <div className="matrix-layout">
                  <div className="matrix-canvas-container">
                    <div className="matrix-quadrants-grid">
                      {(['major_project', 'quick_win', 'thankless_task', 'fill_in']).map((key) => (
                        <div key={key} className={`quadrant-box quad-${key.replace(/_/g, '-')}`}>
                          <div className="quad-label">
                            <span>{QUADRANTS[key].label}</span>
                            <small>{QUADRANTS[key].desc}</small>
                          </div>
                        </div>
                      ))}

                      {items.map((item) => {
                        const value = item.value_vs_effort?.value || 5;
                        const effort = item.value_vs_effort?.effort || 5;
                        const left = ((effort - 1) / 9) * 80 + 10;
                        const bottom = ((value - 1) / 9) * 80 + 10;
                        const isSelected = selected?.id === item.id;
                        return (
                          <button
                            key={item.id}
                            type="button"
                            className={['matrix-node', isSelected && 'selected'].filter(Boolean).join(' ')}
                            style={{ left: `${left}%`, bottom: `${bottom}%` }}
                            aria-pressed={isSelected}
                            aria-label={`${item.name}, value ${value}, effort ${effort}`}
                            onClick={() => setSelected(item)}
                          >
                            <span className="node-dot" />
                            <span className="node-label">{item.name}</span>
                          </button>
                        );
                      })}
                    </div>

                    <div className="axis-label-x">Effort →</div>
                    <div className="axis-label-y">Value →</div>
                  </div>

                  <Card>
                    <CardBody className="stack stack-md">
                      {selected ? (
                        <>
                          <div className="inspector-header">
                            <h3 className="section-title">{selected.name}</h3>
                            <Badge tone={QUADRANTS[selected.value_vs_effort?.quadrant]?.tone || 'neutral'}>
                              {QUADRANTS[selected.value_vs_effort?.quadrant]?.label || 'Unclassified'}
                            </Badge>
                          </div>

                          <p className="inspector-desc">{selected.description || 'No description yet.'}</p>

                          <div className="slider-group">
                            <label htmlFor="matrix-value">
                              Value to customers
                              <strong>{selected.value_vs_effort?.value || 7}/10</strong>
                            </label>
                            <input
                              id="matrix-value"
                              type="range"
                              min="1"
                              max="10"
                              step="0.5"
                              value={selected.value_vs_effort?.value || 7}
                              onChange={(e) =>
                                updateScore(selected.id, 'value_vs_effort', 'value', e.target.value)
                              }
                            />
                          </div>

                          <div className="slider-group">
                            <label htmlFor="matrix-effort">
                              Implementation effort
                              <strong>{selected.value_vs_effort?.effort || 4}/10</strong>
                            </label>
                            <input
                              id="matrix-effort"
                              type="range"
                              min="1"
                              max="10"
                              step="0.5"
                              value={selected.value_vs_effort?.effort || 4}
                              onChange={(e) =>
                                updateScore(selected.id, 'value_vs_effort', 'effort', e.target.value)
                              }
                            />
                          </div>

                          {selected.ai_rationale && (
                            <div className="ai-note-box">
                              <strong>Why this was scored here</strong>
                              <p>{selected.ai_rationale}</p>
                            </div>
                          )}
                        </>
                      ) : (
                        <EmptyState icon="target" title="Nothing selected">
                          Pick an initiative on the matrix to inspect and adjust its value and effort
                          scores.
                        </EmptyState>
                      )}
                    </CardBody>
                  </Card>
                </div>
              </CardBody>
            </Card>
          )}

          {tab === 'moscow' && (
            <div className="moscow-columns-grid">
              {MOSCOW_COLUMNS.map((column) => {
                const columnItems = items.filter((i) => (i.moscow || 'should_have') === column.id);
                return (
                  <Card key={column.id} className="moscow-column">
                    <div className="moscow-col-header">
                      <h3 className="section-title">{column.label}</h3>
                      <span className="badge-num">{columnItems.length}</span>
                    </div>
                    <p className="moscow-desc">{column.note}</p>

                    <div className="moscow-items-list">
                      {columnItems.length === 0 && <p className="text-xs text-light">Empty</p>}
                      {columnItems.map((item) => (
                        <div key={item.id} className="moscow-card">
                          <h4 className="moscow-item-name">{item.name}</h4>
                          <div className="moscow-meta">
                            <span className="badge badge-neutral">RICE {Math.round(item.rice?.score || 0)}</span>
                            {item.value_vs_effort?.quadrant && (
                              <Badge tone={QUADRANTS[item.value_vs_effort.quadrant]?.tone || 'neutral'}>
                                {QUADRANTS[item.value_vs_effort.quadrant]?.label}
                              </Badge>
                            )}
                          </div>
                          <div className="moscow-move-row">
                            <label htmlFor={`moscow-${item.id}`}>Move to</label>
                            <select
                              id={`moscow-${item.id}`}
                              className="moscow-select-sm"
                              value={item.moscow || 'should_have'}
                              onChange={(e) => updateScore(item.id, 'moscow', 'moscow', e.target.value)}
                            >
                              {MOSCOW_COLUMNS.map((option) => (
                                <option key={option.id} value={option.id}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}

          {tab === 'weighted' && (
            <div className="stack">
              <Card>
                <CardHeader
                  title="Your weighting model"
                  hint="Set what the organisation values, then re-rank every initiative against it."
                  actions={
                    <Button
                      variant="secondary"
                      icon="save"
                      loading={busyAction === 'weights'}
                      onClick={saveWeights}
                    >
                      Save as workspace default
                    </Button>
                  }
                />
                <CardBody>
                  <div className="weights-grid">
                    {WEIGHT_FIELDS.map((field) => (
                      <div key={field.key} className="weight-slider-card">
                        <div className="weight-header">
                          <span>
                            <label htmlFor={field.key}>{field.label}</label>
                          </span>
                          <strong>{Math.round(weights[field.key] * 100)}%</strong>
                        </div>
                        <input
                          id={field.key}
                          type="range"
                          min="0.05"
                          max="0.7"
                          step="0.05"
                          value={weights[field.key]}
                          onChange={(e) =>
                            setWeights((prev) => ({ ...prev, [field.key]: parseFloat(e.target.value) }))
                          }
                        />
                      </div>
                    ))}
                  </div>
                </CardBody>
              </Card>

              <Card flush>
                <CardHeader title="Weighted leaderboard" hint="Recomputed from the sliders above." />
                <div className="table-responsive">
                  <table className="table">
                    <thead>
                      <tr>
                        <th scope="col">Rank</th>
                        <th scope="col">Initiative</th>
                        {WEIGHT_FIELDS.map((field) => (
                          <th key={field.key} scope="col">
                            {field.label}
                          </th>
                        ))}
                        <th scope="col">Weighted total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {weightedRanked.map((item, index) => (
                        <tr key={item.id}>
                          <td>
                            <span className="rank-badge">{index + 1}</span>
                          </td>
                          <td className="text-semibold">{item.name}</td>
                          <td>{item.weighted?.customer_demand_score ?? 70} / 100</td>
                          <td>{item.weighted?.business_impact_score ?? 70} / 100</td>
                          <td>{item.weighted?.feasibility_score ?? 70} / 100</td>
                          <td>{item.weighted?.risk_mitigation_score ?? 70} / 100</td>
                          <td>
                            <div className="score-progress-box">
                              <span className="weighted-score-num">{item.weightedTotal} pts</span>
                              <div className="progress-track">
                                <span style={{ width: `${Math.min(100, item.weightedTotal)}%` }} />
                              </div>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}
        </>
      )}

      <Modal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        title="Add an initiative"
        description="Anything can be ranked — a feature, a fix, or a piece of platform work."
        icon="plus"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowAdd(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              icon="plus"
              loading={busyAction === 'add'}
              disabled={!draft.name.trim()}
              onClick={addItem}
            >
              Add initiative
            </Button>
          </>
        }
      >
        <div className="modal-form">
          <Input
            label="Name"
            placeholder="e.g. Biometric sign-in"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            autoFocus
          />
          <Textarea
            label="Description and user value"
            rows={2}
            placeholder="What the customer asked for, and why it matters."
            value={draft.description}
            onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          />
          <div className="form-row">
            <div className="form-group flex-1">
              <Select
                label="Category"
                value={draft.category}
                onChange={(e) => setDraft({ ...draft, category: e.target.value })}
              >
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-group flex-1">
              <Select
                label="MoSCoW tier"
                value={draft.moscow}
                onChange={(e) => setDraft({ ...draft, moscow: e.target.value })}
              >
                {MOSCOW_COLUMNS.map((column) => (
                  <option key={column.id} value={column.id}>
                    {column.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group flex-1">
              <Input
                label="Reach (users / month)"
                type="number"
                value={draft.reach}
                onChange={(e) => setDraft({ ...draft, reach: e.target.value })}
              />
            </div>
            <div className="form-group flex-1">
              <Select
                label="Impact"
                value={draft.impact}
                onChange={(e) => setDraft({ ...draft, impact: e.target.value })}
              >
                {IMPACT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>
            <div className="form-group flex-1">
              <Input
                label="Effort (sprints)"
                type="number"
                step="0.5"
                value={draft.effort}
                onChange={(e) => setDraft({ ...draft, effort: e.target.value })}
              />
            </div>
          </div>
        </div>
      </Modal>

      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete this initiative?"
        description="It will be removed from every framework."
        icon="trash"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              Keep it
            </Button>
            <Button variant="danger" icon="trash" onClick={confirmDelete}>
              Delete
            </Button>
          </>
        }
      >
        <div className="modal-body">
          <p className="prose">{pendingDelete?.name}</p>
        </div>
      </Modal>
    </div>
  );
}
