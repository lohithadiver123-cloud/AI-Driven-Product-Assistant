import { Suspense, ViewTransition } from 'react';
import { Outlet } from 'react-router-dom';
import Navbar from './Navbar';
import FloatingCopilot from './FloatingCopilot';
import { WorkspaceProvider } from '../context/WorkspaceContext';
import { Skeleton, SkeletonStatGrid, SkeletonCardGrid } from './ui';

/**
 * Shape shown while a route's code and its first data payload are in flight.
 * It mirrors a typical page, so the shell settles instead of flashing empty.
 */
function RouteFallback() {
  return (
    <div className="page-container" role="status" aria-label="Loading page">
      <div className="page-heading">
        <Skeleton className="skeleton-title" style={{ width: 260, height: 28 }} />
        <Skeleton className="skeleton-line" style={{ width: 420 }} />
      </div>
      <SkeletonStatGrid count={3} />
      <SkeletonCardGrid count={2} />
    </div>
  );
}

/**
 * The authenticated shell: dark top bar, one page region, the floating copilot.
 * Route-level code splitting means the fallback below is seen once per page,
 * not a blank screen.
 */
export default function AppLayout() {
  return (
    <WorkspaceProvider>
      <div className="app-container">
        <Navbar />
        <main className="app-main">
          {/* The skeleton is only ever seen while a route's code and its first
              payload are in flight. It sinks away as the real page arrives,
              so the swap reads as content landing rather than as a flash.

              Deliberately only the fallback is wrapped: the entering page is
              already a view-transition boundary of its own (see
              ViewTransitions.jsx), and a wrapper here would own the mutation
              and swallow it. */}
          <Suspense
            fallback={
              <ViewTransition exit="vt-slide-down">
                <RouteFallback />
              </ViewTransition>
            }
          >
            <Outlet />
          </Suspense>
        </main>
        <FloatingCopilot />
      </div>
    </WorkspaceProvider>
  );
}
