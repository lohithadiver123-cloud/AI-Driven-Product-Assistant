import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../services/api';

const POLL_MS = 1500;

/**
 * Watch the background analysis of a workspace.
 *
 * Analysis runs on the server now, so a page never waits on it — it starts the job,
 * reads this status while the work happens, and picks the result up when the state
 * leaves "running". `onFinished` is called once per run with the final status, which is
 * where a page should re-fetch its insights.
 *
 *   const { status, refresh, run } = useAnalysisStatus(workspaceId, async (s) => {
 *     if (s.state === 'completed') await fetchInsights(workspaceId);
 *   });
 */
export default function useAnalysisStatus(workspaceId, onFinished) {
  const [status, setStatus] = useState(null);
  const finishRef = useRef(onFinished);
  const seenRunning = useRef(false);

  useEffect(() => {
    finishRef.current = onFinished;
  }, [onFinished]);

  const refresh = useCallback(async () => {
    if (!workspaceId) {
      setStatus(null);
      return null;
    }
    try {
      // Never served from the GET cache: a status read that returned a stale answer
      // would leave the spinner running after the job had finished.
      const { data } = await api.get(`/insights/${workspaceId}/status`, { cache: false });
      setStatus(data);
      return data;
    } catch {
      return null;
    }
  }, [workspaceId]);

  /** Queue an analysis and start watching it. Resolves with the job status. */
  const run = useCallback(
    async (path) => {
      const { data } = await api.post(path || `/insights/${workspaceId}/analyze`);
      if (data && data.state) setStatus(data);
      return data;
    },
    [workspaceId]
  );

  // Switching workspace drops the previous one's status and asks what this one is doing.
  useEffect(() => {
    seenRunning.current = false;
    refresh();
  }, [refresh]);

  // Poll while the job is live. The effect re-arms itself on each new status object and
  // stops the moment the state changes, so an idle workspace costs exactly one request.
  useEffect(() => {
    if (!status || status.state !== 'running') return undefined;
    seenRunning.current = true;
    const timer = setTimeout(refresh, POLL_MS);
    return () => clearTimeout(timer);
  }, [status, refresh]);

  // Announce the end of a run the watcher actually saw start.
  useEffect(() => {
    if (!status || !seenRunning.current) return;
    if (status.state === 'running') return;
    seenRunning.current = false;
    finishRef.current?.(status);
  }, [status]);

  return { status, refresh, run };
}
