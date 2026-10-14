import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import api from '../services/api';

/**
 * The active workspace, app-wide.
 *
 * Every screen used to fetch `/workspaces` and keep its own selected id, so
 * picking a workspace on the Dashboard left Insights and the PRD board on a
 * different one. One provider now owns the list and the selection: fetch once,
 * mirror it into `localStorage`, and let pages subscribe. The id survives a
 * reload and a route change; switching it re-renders every consumer at once.
 *
 * `localStorage` doubles as the hand-off channel for the floating copilot,
 * which lives outside any page, and as cross-tab sync via the `storage` event.
 */
const STORAGE_KEY = 'pm_copilot_active_ws';

export const workspaceIdOf = (workspace) => workspace?._id || workspace?.id || '';

const WorkspaceContext = createContext(null);

export function WorkspaceProvider({ children }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [activeId, setActiveId] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) || '';
    } catch {
      return '';
    }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const persist = useCallback((id) => {
    setActiveId(id);
    api.clearCache?.();
    try {
      if (id) localStorage.setItem(STORAGE_KEY, id);
      else localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* private mode — the selection still works for this session */
    }
  }, []);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.get('/workspaces');
      const list = Array.isArray(data) ? data : [];
      setWorkspaces(list);
      setError('');
      return list;
    } catch {
      // Keep whatever list we already have. Swapping in an empty one here
      // would look identical to "every workspace was deleted" and make the
      // reconciliation below forget the user's selection over a blip.
      setError('Could not load your workspaces.');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // The remembered id can outlive the workspace it points at (deleted in
  // another tab, a different account). Fall back instead of stranding every
  // page on an id the API no longer knows — but never reconcile against a
  // failed fetch, or a network blip would silently move everyone to whatever
  // workspace happens to be first.
  useEffect(() => {
    if (loading || error) return;
    const known = activeId && workspaces.some((ws) => workspaceIdOf(ws) === activeId);
    if (workspaces.length > 0 && !known) persist(workspaceIdOf(workspaces[0]));
    else if (workspaces.length === 0 && activeId) persist('');
  }, [loading, error, workspaces, activeId, persist]);

  // Another tab switched workspace — follow it so both stay in step.
  useEffect(() => {
    const onStorage = (event) => {
      if (event.key === STORAGE_KEY) setActiveId(event.newValue || '');
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setActive = useCallback(
    (id) => {
      if (id) persist(id);
    },
    [persist]
  );

  const createWorkspace = useCallback(
    async (name) => {
      const { data } = await api.post('/workspaces', { name: name.trim() });
      const id = workspaceIdOf(data);
      await refresh();
      if (id) persist(id);
      return data;
    },
    [refresh, persist]
  );

  const activeWorkspace = useMemo(
    () => workspaces.find((ws) => workspaceIdOf(ws) === activeId) || null,
    [workspaces, activeId]
  );

  const value = useMemo(
    () => ({
      workspaces,
      activeId,
      activeWorkspace,
      loading,
      /** True once the first `/workspaces` call has settled, pass or fail. */
      ready: !loading,
      error,
      setActive,
      refresh,
      createWorkspace,
    }),
    [workspaces, activeId, activeWorkspace, loading, error, setActive, refresh, createWorkspace]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspaces() {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error('useWorkspaces must be used inside a WorkspaceProvider');
  }
  return context;
}
