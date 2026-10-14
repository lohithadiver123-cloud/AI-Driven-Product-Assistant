import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../services/api';
import Icon from '../components/Icon';
import { useBusy } from '../context/BusyContext';
import { useWorkspaces } from '../context/WorkspaceContext';
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  IconButton,
  Input,
  Modal,
  PageHeader,
  SearchInput,
  Segmented,
  Select,
  SkeletonBoard,
  SkeletonTable,
  Textarea,
  Toolbar,
} from '../components/ui';

const COLUMNS = [
  { id: 'backlog', label: 'Backlog', tone: 'backlog' },
  { id: 'in_progress', label: 'In progress', tone: 'progress' },
  { id: 'in_review', label: 'In review', tone: 'review' },
  { id: 'done', label: 'Done', tone: 'done' },
];

const STATUS_LABELS = {
  backlog: 'Backlog',
  in_progress: 'In progress',
  in_review: 'In review',
  done: 'Done',
};

const PRIORITY_TONE = { high: 'danger', medium: 'warning', low: 'neutral' };

const POINT_OPTIONS = [1, 2, 3, 5, 8, 13];

/**
 * `/insights/{id}/clusters` answers with a bare JSON array; accept a wrapped
 * object as well so the cluster picker can never collapse to zero silently.
 */
const asList = (payload, key) => {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload && payload[key])) return payload[key];
  return [];
};

/**
 * User stories — the sprint view of the roadmap.
 *
 * Board and list are the same data in two densities, driven by one segmented
 * control. Status, edit and delete all live on the card they belong to, so the
 * page has a single primary action: generate.
 */
export default function UserStoriesWorkspace() {
  const location = useLocation();
  const { begin } = useBusy();
  const initialPrdId = new URLSearchParams(location.search).get('prd_id') || '';

  const { activeId: selectedWorkspace, ready } = useWorkspaces();
  const [prds, setPrds] = useState(() => (selectedWorkspace ? api.getCached(`/prd/workspace/${selectedWorkspace}`) || [] : []));
  const [clusters, setClusters] = useState(() => (selectedWorkspace ? api.getCached(`/insights/${selectedWorkspace}/clusters`) || [] : []));
  const [prdFilter, setPrdFilter] = useState(initialPrdId);
  const [stories, setStories] = useState(() => (selectedWorkspace ? api.getCached(initialPrdId ? `/user-stories/workspace/${selectedWorkspace}?prd_id=${initialPrdId}` : `/user-stories/workspace/${selectedWorkspace}`) || [] : []));

  const [loading, setLoading] = useState(() => !selectedWorkspace || !api.getCached(initialPrdId ? `/user-stories/workspace/${selectedWorkspace}?prd_id=${initialPrdId}` : `/user-stories/workspace/${selectedWorkspace}`));
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [query, setQuery] = useState('');
  const [view, setView] = useState('kanban');
  const [expanded, setExpanded] = useState(null);
  // The story currently being dragged between board columns.
  const [dragStory, setDragStory] = useState(null);

  const [showGenerate, setShowGenerate] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [source, setSource] = useState('prd');
  const [genPrdId, setGenPrdId] = useState(initialPrdId);
  const [genClusterId, setGenClusterId] = useState('');
  const [genPrompt, setGenPrompt] = useState('');
  const [genCount, setGenCount] = useState('5');
  const [genPersona, setGenPersona] = useState('');

  const [editing, setEditing] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);

  // Sync query params when navigating
  useEffect(() => {
    const currentPrdId = new URLSearchParams(location.search).get('prd_id') || '';
    if (currentPrdId) {
      setPrdFilter(currentPrdId);
      setGenPrdId(currentPrdId);
    }
  }, [location.search]);

  // Handoff from Copilot or other pages via route state
  useEffect(() => {
    if (location.state?.prefill) {
      const pf = location.state.prefill;
      if (pf.source) setSource(pf.source);
      if (pf.prompt) setGenPrompt(pf.prompt);
      if (pf.prdId) setGenPrdId(pf.prdId);
      if (pf.clusterId) setGenClusterId(pf.clusterId);
      if (pf.count) setGenCount(String(pf.count));
      if (pf.persona) setGenPersona(pf.persona);
      setShowGenerate(true);
    }
  }, [location.state]);

  const loadStories = useCallback(async (workspaceId, prdId) => {
    if (!workspaceId) return;
    const url = prdId
      ? `/user-stories/workspace/${workspaceId}?prd_id=${prdId}`
      : `/user-stories/workspace/${workspaceId}`;
    if (!api.getCached(url)) {
      setLoading(true);
    }
    setError('');
    try {
      const { data } = await api.get(url);
      setStories(data);
    } catch {
      setError('Could not load user stories for this workspace.');
      setStories([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadPrdsAndClusters = useCallback(async (workspaceId) => {
    const [prdResult, clusterResult] = await Promise.allSettled([
      api.get(`/prd/workspace/${workspaceId}`),
      api.get(`/insights/${workspaceId}/clusters`),
    ]);
    if (prdResult.status === 'fulfilled') setPrds(prdResult.value.data || []);
    if (clusterResult.status === 'fulfilled') {
      setClusters(asList(clusterResult.value.data, 'clusters'));
    }
  }, []);

  // `?prd_id=` scopes the very first load only — after that, moving workspace
  // resets the PRD filter instead of stranding it on a document that may not
  // exist in the next workspace.
  const firstLoad = useRef(true);

  useEffect(() => {
    if (!selectedWorkspace) return undefined;
    const prdId = firstLoad.current ? initialPrdId : '';
    firstLoad.current = false;
    if (!prdId) setPrdFilter('');
    loadPrdsAndClusters(selectedWorkspace);
    loadStories(selectedWorkspace, prdId);
    return undefined;
  }, [selectedWorkspace, initialPrdId, loadPrdsAndClusters, loadStories]);

  useEffect(() => {
    if (ready && !selectedWorkspace) setLoading(false);
  }, [ready, selectedWorkspace]);

  const changePrdFilter = (event) => {
    const prdId = event.target.value;
    setPrdFilter(prdId);
    loadStories(selectedWorkspace, prdId);
  };

  const changeStatus = async (storyId, status) => {
    const previous = stories;
    setStories((prev) => prev.map((s) => (s.id === storyId ? { ...s, status } : s)));
    try {
      await api.patch(`/user-stories/${storyId}/status`, { status });
    } catch {
      setStories(previous);
      setError('Could not move that story. The board has been put back.');
    }
  };

  const confirmDelete = async () => {
    const story = pendingDelete;
    setPendingDelete(null);
    if (!story) return;
    const previous = stories;
    setStories((prev) => prev.filter((s) => s.id !== story.id));
    try {
      await api.delete(`/user-stories/${story.id}`);
      setNotice(`Deleted “${story.title}”.`);
    } catch {
      setStories(previous);
      setError('Could not delete that story.');
    }
  };

  const handleGenerate = async (event) => {
    event.preventDefault();
    if (!selectedWorkspace) return;

    const done = begin('Generating user stories');
    setGenerating(true);
    setError('');
    try {
      await api.post('/user-stories/generate', {
        workspace_id: selectedWorkspace,
        prd_id: source === 'prd' ? genPrdId : undefined,
        feature_cluster_id: source === 'cluster' ? genClusterId : undefined,
        custom_prompt: source === 'custom' ? genPrompt : undefined,
        count: parseInt(genCount, 10) || 5,
        persona: genPersona || undefined,
      });
      setShowGenerate(false);
      setNotice('New stories generated.');
      await loadStories(selectedWorkspace, prdFilter);
    } catch (err) {
      setError(err.response?.data?.detail || 'Story generation failed. Try again in a moment.');
    } finally {
      setGenerating(false);
      done();
    }
  };

  const handleSaveEdit = async (event) => {
    event.preventDefault();
    if (!editing) return;
    try {
      const { data } = await api.put(`/user-stories/${editing.id}`, {
        title: editing.title,
        role: editing.role,
        action: editing.action,
        benefit: editing.benefit,
        full_statement: `As a ${editing.role}, I want to ${editing.action}, so that ${editing.benefit}.`,
        story_points: parseInt(editing.story_points, 10),
        t_shirt_size: editing.t_shirt_size,
        priority: editing.priority,
        status: editing.status,
      });
      setStories((prev) => prev.map((s) => (s.id === editing.id ? data : s)));
      setEditing(null);
    } catch {
      setError('Could not save those changes.');
    }
  };

  const filtered = stories.filter((story) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return [story.title, story.full_statement, story.role, story.action, story.benefit]
      .filter(Boolean)
      .some((field) => field.toLowerCase().includes(q));
  });

  const countBy = (status) => filtered.filter((s) => (s.status || 'backlog') === status).length;

  const exportCsv = () => {
    if (filtered.length === 0) return;
    const quote = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const rows = filtered.map((s) =>
      [s.id, quote(s.title), quote(s.role), quote(s.action), quote(s.benefit), s.story_points || 3, s.t_shirt_size || 'M', s.priority || 'medium', s.status || 'backlog'].join(',')
    );
    const csv = ['ID,Title,Role,Action,Benefit,Points,Size,Priority,Status', ...rows].join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = `user-stories-${selectedWorkspace}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const renderStoryActions = (story) => (
    <div className="story-footer-btns">
      <IconButton icon="pencil" label={`Edit ${story.title}`} size="sm" onClick={() => setEditing({ ...story })} />
      <IconButton
        icon="trash"
        variant="danger"
        size="sm"
        label={`Delete ${story.title}`}
        onClick={() => setPendingDelete(story)}
      />
    </div>
  );

  const statusSelect = (story) => (
    <>
      <label className="sr-only" htmlFor={`status-${story.id}`}>
        Status for {story.title}
      </label>
      <select
        id={`status-${story.id}`}
        className="status-dropdown-sm"
        value={story.status || 'backlog'}
        onChange={(e) => changeStatus(story.id, e.target.value)}
      >
        {Object.entries(STATUS_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </>
  );

  return (
    <div className="page-container">
      <PageHeader
        icon="clipboard"
        title="User stories"
        trail="stories"
        description="Sprint-ready stories with Gherkin acceptance criteria, Fibonacci points and T-shirt estimates."
        actions={
          <Button
            variant="primary"
            icon="sparkle"
            disabled={!selectedWorkspace}
            onClick={() => setShowGenerate(true)}
          >
            Generate stories
          </Button>
        }
      />

      {notice && <Alert variant="success">{notice}</Alert>}
      {error && <Alert variant="error">{error}</Alert>}

      <Toolbar
        left={
          <>
            <SearchInput
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search title, role or action"
              width={280}
            />
            <Select label="Source PRD" value={prdFilter} onChange={changePrdFilter} style={{ minWidth: 220 }}>
              <option value="">All PRDs</option>
              {prds.map((prd) => (
                <option key={prd.id} value={prd.id}>
                  {prd.title}
                </option>
              ))}
            </Select>
          </>
        }
        right={
          <>
            {query && (
              <Button variant="ghost" size="sm" icon="x" onClick={() => setQuery('')}>
                Clear
              </Button>
            )}
            <Button size="sm" variant="secondary" icon="download" disabled={!filtered.length} onClick={exportCsv}>
              Export CSV
            </Button>
            <Segmented
              label="View mode"
              value={view}
              onChange={setView}
              options={[
                { value: 'kanban', label: 'Board', icon: 'columns' },
                { value: 'list', label: 'List', icon: 'table' },
              ]}
            />
          </>
        }
      />

      {/* No stat cards: the board's own column headers already carry these
          counts, and the list view shows each story's status on its row. */}

      {loading ? (
        view === 'kanban' ? (
          <SkeletonBoard columns={4} />
        ) : (
          <Card flush>
            <SkeletonTable rows={6} columns={6} />
          </Card>
        )
      ) : filtered.length === 0 ? (
        <Card>
          <EmptyState
            icon="clipboard"
            title={query || prdFilter ? 'No stories match this filter' : 'No user stories yet'}
            actions={
              query || prdFilter ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuery('');
                    setPrdFilter('');
                    loadStories(selectedWorkspace, '');
                  }}
                >
                  Clear filters
                </Button>
              ) : (
                <Button variant="primary" icon="sparkle" onClick={() => setShowGenerate(true)}>
                  Generate stories
                </Button>
              )
            }
          >
            {query || prdFilter
              ? 'Widen the search or switch back to all PRDs.'
              : 'Turn a PRD or a feature cluster into sprint-ready stories with acceptance criteria.'}
          </EmptyState>
        </Card>
      ) : view === 'kanban' ? (
        <div className="kanban-board">
          {COLUMNS.map((column) => {
            const columnStories = filtered.filter((s) => (s.status || 'backlog') === column.id);
            return (
              <section
                key={column.id}
                className={`kanban-column${dragStory ? ' is-drop-target' : ''}`}
                aria-label={column.label}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (dragStory) changeStatus(dragStory.id, column.id);
                  setDragStory(null);
                }}
              >
                <header className={`kanban-col-header tone-${column.tone}`}>
                  <span className="col-label">{column.label}</span>
                  <span className="badge-num">{columnStories.length}</span>
                </header>

                <div className="kanban-cards-container">
                  {/*
                   * An empty column is a target, not a dead end: it keeps a
                   * dashed drop zone so there is somewhere obvious to drag to.
                   */}
                  {columnStories.length === 0 && (
                    <div className="kanban-dropzone">
                      <Icon name="plus" size={14} />
                      <span>Drop a story here</span>
                    </div>
                  )}

                  {columnStories.map((story) => {
                    const isOpen = expanded === story.id;
                    const scenarios = story.acceptance_criteria?.length || 0;
                    return (
                      <article
                        key={story.id}
                        className="story-card"
                        draggable
                        onDragStart={() => setDragStory(story)}
                        onDragEnd={() => setDragStory(null)}
                      >
                        {/*
                         * Collapsed by default: title, points and priority are
                         * what a board is scanned for. The statement and the
                         * Gherkin scenarios are one click away, and the status
                         * moved out of the card entirely — dragging between
                         * columns is the way to change it.
                         */}
                        <div className="story-top-row">
                          <div className="story-points-group">
                            <span className="badge badge-accent">{story.story_points || 3} pts</span>
                            <span className="badge badge-neutral" title={`T-shirt size ${story.t_shirt_size || 'M'}`}>
                              {story.t_shirt_size || 'M'}
                            </span>
                          </div>
                          <Badge tone={PRIORITY_TONE[(story.priority || 'medium').toLowerCase()] || 'neutral'}>
                            {story.priority || 'medium'}
                          </Badge>
                        </div>

                        <h3 className="story-title">{story.title}</h3>

                        <div className="story-card-footer">
                          <button
                            type="button"
                            className="btn-toggle-criteria"
                            aria-expanded={isOpen}
                            onClick={() => setExpanded(isOpen ? null : story.id)}
                          >
                            <Icon name={isOpen ? 'chevronDown' : 'chevronRight'} size={12} />
                            {isOpen ? 'Hide story' : `Story${scenarios ? ` · ${scenarios} scenarios` : ''}`}
                          </button>
                          {renderStoryActions(story)}
                        </div>

                        {isOpen && (
                          <div className="stack stack-sm story-detail">
                            <p className="story-statement">
                              <strong>As a</strong> <span className="highlight-role">{story.role}</span>,{' '}
                              <strong>I want to</strong> {story.action}, <strong>so that</strong> {story.benefit}.
                            </p>

                            {story.acceptance_criteria?.length > 0 && (
                              <div className="criteria-dropdown">
                                {story.acceptance_criteria.map((criteria) => (
                                  <div key={criteria.scenario} className="gherkin-scenario">
                                    <div className="scenario-title">Scenario: {criteria.scenario}</div>
                                    <div className="gherkin-line">
                                      <strong>Given</strong> {criteria.given}
                                    </div>
                                    <div className="gherkin-line">
                                      <strong>When</strong> {criteria.when}
                                    </div>
                                    <div className="gherkin-line">
                                      <strong>Then</strong> {criteria.then}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <Card flush>
          <div className="table-responsive">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Status</th>
                  <th scope="col">Story</th>
                  <th scope="col">Points</th>
                  <th scope="col">Size</th>
                  <th scope="col">Priority</th>
                  <th scope="col">Criteria</th>
                  <th scope="col" className="tight">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((story) => (
                  <tr key={story.id}>
                    <td>{statusSelect(story)}</td>
                    <td>
                      <div className="table-primary">
                        <strong>{story.title}</strong>
                        <span className="table-secondary">
                          As a {story.role}, I want to {story.action}
                        </span>
                      </div>
                    </td>
                    <td>
                      <span className="badge badge-accent">{story.story_points || 3} pts</span>
                    </td>
                    <td>
                      <span className="badge badge-neutral">{story.t_shirt_size || 'M'}</span>
                    </td>
                    <td>
                      <Badge tone={PRIORITY_TONE[(story.priority || 'medium').toLowerCase()] || 'neutral'}>
                        {story.priority || 'medium'}
                      </Badge>
                    </td>
                    <td className="text-muted">{story.acceptance_criteria?.length || 0} scenarios</td>
                    <td>{renderStoryActions(story)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Modal
        open={showGenerate}
        onClose={() => !generating && setShowGenerate(false)}
        title="Generate user stories"
        description="Pick what the stories should be grounded in, then how many you need."
        icon="sparkle"
        footer={
          generating ? null : (
            <>
              <Button variant="secondary" onClick={() => setShowGenerate(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                icon="sparkle"
                onClick={handleGenerate}
                disabled={
                  source === 'prd' ? !genPrdId : source === 'cluster' ? !genClusterId : !genPrompt.trim()
                }
              >
                Generate
              </Button>
            </>
          )
        }
      >
        {generating ? (
          <div className="modal-generating-state">
            <span className="spinner spinner-lg" />
            <h3>Synthesising stories</h3>
            <p className="text-muted">
              Writing story statements, Gherkin acceptance criteria and Fibonacci estimates.
            </p>
          </div>
        ) : (
          <div className="modal-form">
            <div className="field">
              <span className="field-label">Grounded in</span>
              <Segmented
                label="Generation source"
                value={source}
                onChange={setSource}
                options={[
                  { value: 'prd', label: `PRD (${prds.length})`, icon: 'file' },
                  { value: 'cluster', label: `Cluster (${clusters.length})`, icon: 'layers' },
                  { value: 'custom', label: 'Custom topic', icon: 'pencil' },
                ]}
              />
            </div>

            {source === 'prd' && (
              <Select
                label="PRD document"
                value={genPrdId}
                onChange={(e) => setGenPrdId(e.target.value)}
              >
                <option value="">Choose a PRD…</option>
                {prds.map((prd) => (
                  <option key={prd.id} value={prd.id}>
                    {prd.title}
                  </option>
                ))}
              </Select>
            )}

            {source === 'cluster' && (
              <Select
                label="Feature cluster"
                value={genClusterId}
                onChange={(e) => setGenClusterId(e.target.value)}
              >
                <option value="">Choose a cluster…</option>
                {clusters.map((cluster) => (
                  <option key={cluster.id} value={cluster.id}>
                    {cluster.cluster_name} — {cluster.demand_level} demand
                  </option>
                ))}
              </Select>
            )}

            {source === 'custom' && (
              <Textarea
                label="Capability or requirement"
                rows={3}
                placeholder="e.g. One-click account recovery with automated identity verification"
                value={genPrompt}
                onChange={(e) => setGenPrompt(e.target.value)}
              />
            )}

            <div className="form-row">
              <div className="form-group flex-1">
                <Select label="How many" value={genCount} onChange={(e) => setGenCount(e.target.value)}>
                  <option value="3">3 — a focused slice</option>
                  <option value="5">5 — a standard sprint</option>
                  <option value="8">8 — comprehensive coverage</option>
                </Select>
              </div>
              <div className="form-group flex-1">
                <Input
                  label="Target persona (optional)"
                  placeholder="e.g. Mobile user, Admin"
                  value={genPersona}
                  onChange={(e) => setGenPersona(e.target.value)}
                />
              </div>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title="Edit story"
        icon="pencil"
        footer={
          <>
            <Button variant="secondary" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={handleSaveEdit}>
              Save changes
            </Button>
          </>
        }
      >
        {editing && (
          <div className="modal-form">
            <Input
              label="Title"
              value={editing.title || ''}
              onChange={(e) => setEditing({ ...editing, title: e.target.value })}
            />
            <Input
              label="As a (role)"
              value={editing.role || ''}
              onChange={(e) => setEditing({ ...editing, role: e.target.value })}
            />
            <Input
              label="I want to (action)"
              value={editing.action || ''}
              onChange={(e) => setEditing({ ...editing, action: e.target.value })}
            />
            <Input
              label="So that (benefit)"
              value={editing.benefit || ''}
              onChange={(e) => setEditing({ ...editing, benefit: e.target.value })}
            />
            <div className="form-row">
              <div className="form-group flex-1">
                <Select
                  label="Story points"
                  value={editing.story_points}
                  onChange={(e) => setEditing({ ...editing, story_points: e.target.value })}
                >
                  {POINT_OPTIONS.map((points) => (
                    <option key={points} value={points}>
                      {points} {points === 1 ? 'point' : 'points'}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="form-group flex-1">
                <Select
                  label="T-shirt size"
                  value={editing.t_shirt_size}
                  onChange={(e) => setEditing({ ...editing, t_shirt_size: e.target.value })}
                >
                  {['XS', 'S', 'M', 'L', 'XL'].map((size) => (
                    <option key={size} value={size}>
                      {size}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="form-group flex-1">
                <Select
                  label="Priority"
                  value={editing.priority}
                  onChange={(e) => setEditing({ ...editing, priority: e.target.value })}
                >
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </Select>
              </div>
            </div>
          </div>
        )}
      </Modal>

      <Modal
        open={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        title="Delete this story?"
        description="This cannot be undone."
        icon="trash"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPendingDelete(null)}>
              Keep it
            </Button>
            <Button variant="danger" icon="trash" onClick={confirmDelete}>
              Delete story
            </Button>
          </>
        }
      >
        <div className="modal-body">
          <p className="prose">{pendingDelete?.title}</p>
        </div>
      </Modal>
    </div>
  );
}
