import { Suspense, ViewTransition, addTransitionType, startTransition } from 'react';
import { SkeletonPage } from './ui';

/**
 * The two transition types this app tags a navigation with.
 *
 * They exist so a page boundary can tell *how* someone arrived. Stepping into
 * the stories a document was broken into reads as depth (nav-forward);
 * stepping back up a level reads as returning (nav-back). Lateral moves — top
 * bar to top bar, a dashboard card to another section — deliberately carry no
 * type, so they fall through to a plain cross-fade rather than implying a
 * hierarchy that is not there.
 */
export const NAV_FORWARD = 'nav-forward';
export const NAV_BACK = 'nav-back';

/**
 * The page boundary every route renders inside (see `page()` below).
 *
 * It wraps a page, never a layout: a layout persists across navigations and
 * would never trigger enter/exit, whereas this belongs to the page it encloses.
 * `default="none"` keeps it out of every unrelated transition (a Suspense
 * resolve, a screen re-fetching its own data), so a page only animates when a
 * page actually changes.
 *
 * Untyped moves cross-fade, which is the honest animation for navigation that
 * has no direction: the top bar, the quick actions on the dashboard, a
 * suggestion in the Copilot. Only the tagged drill-downs slide.
 */
export function PageTransition({ children }) {
  return (
    <ViewTransition
      enter={{ 'nav-forward': 'vt-nav-forward', 'nav-back': 'vt-nav-back', default: 'vt-fade-in' }}
      exit={{ 'nav-forward': 'vt-nav-forward', 'nav-back': 'vt-nav-back', default: 'vt-fade-out' }}
      default="none"
    >
      {children}
    </ViewTransition>
  );
}

/**
 * Wraps a page component in its own page-level boundary.
 *
 * Each route needs a *distinct* component out of this, not one shared wrapper
 * rendered by every route: React reuses a boundary of the same type in the
 * same position, so a shared one would only ever see its children change — an
 * update, never an enter or an exit — and the transition would never fire.
 * One wrapper per page is what makes a navigation a real swap.
 */
export function page(Component) {
  function Page(props) {
    /*
     * The Suspense boundary belongs *outside* the transition, not inside it.
     *
     * Routes are code-split, so on a first visit the component suspends while its chunk
     * arrives. With the transition as the ancestor of a suspending component React cannot
     * begin the transition until that Suspense resolves, gives up, and reports
     * "A ViewTransition timed out because a Navigation stalled" — which is what made
     * navigating look hung. Boundary outside, transition inside means the transition only
     * ever mounts around content that is already there.
     */
    return (
      <Suspense fallback={<SkeletonPage />}>
        <PageTransition>
          <Component {...props} />
        </PageTransition>
      </Suspense>
    );
  }
  Page.displayName = `Page(${Component.displayName || Component.name || 'Page'})`;
  return Page;
}

/**
 * `navigate()` with a transition type attached.
 *
 * React Router already wraps its own state updates in a transition, so a plain
 * `navigate()` animates — it just cannot say what kind of move it was. Tagging
 * the type inside our own startTransition is what a typed page boundary reads.
 */
export function navigateWithType(navigate, to, type = NAV_FORWARD, options) {
  startTransition(() => {
    addTransitionType(type);
    navigate(to, options);
  });
}
