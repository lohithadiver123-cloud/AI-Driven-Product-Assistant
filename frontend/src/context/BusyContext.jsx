import { createContext, useCallback, useContext, useMemo, useState } from 'react';

/**
 * Global "something is happening" flag.
 *
 * Long-running work — an AI analysis, an import, a bulk re-score — calls
 * `begin()` and `end()`. The shell renders the thin progress bar under the
 * navbar while any of them are in flight, so the user always has a visible
 * signal even when the busy surface is scrolled out of view.
 *
 * A counter, not a boolean, so overlapping operations can't clear each other.
 */
const BusyContext = createContext(null);

export function BusyProvider({ children }) {
  const [count, setCount] = useState(0);
  const [label, setLabel] = useState('');

  const begin = useCallback((nextLabel = '') => {
    setCount((c) => c + 1);
    if (nextLabel) setLabel(nextLabel);
    let ended = false;
    return () => {
      if (ended) return;
      ended = true;
      setCount((c) => {
        const next = Math.max(0, c - 1);
        if (next === 0) setLabel('');
        return next;
      });
    };
  }, []);

  const end = useCallback(() => {
    setCount((c) => {
      const next = Math.max(0, c - 1);
      if (next === 0) setLabel('');
      return next;
    });
  }, []);

  /** Wrap an async call so the bar shows for exactly its lifetime. */
  const track = useCallback(
    async (promise, nextLabel) => {
      const done = begin(nextLabel);
      try {
        return await promise;
      } finally {
        done();
      }
    },
    [begin]
  );

  const value = useMemo(
    () => ({ busy: count > 0, label, begin, end, track }),
    [count, label, begin, end, track]
  );

  return <BusyContext.Provider value={value}>{children}</BusyContext.Provider>;
}

export function useBusy() {
  const context = useContext(BusyContext);
  if (!context) {
    throw new Error('useBusy must be used inside a BusyProvider');
  }
  return context;
}
