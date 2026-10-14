import { Link } from 'react-router-dom';
import Icon from '../Icon';

/**
 * Where this screen sits in the product's flow.
 *
 * Feedback becomes an insight, insights get prioritised, priorities become a
 * roadmap, then a PRD, then stories — and the whole point of the app is that
 * the chain is traceable. A page that only says "Roadmap" hides that; the trail
 * says both where you are and what comes next, on every page, the same way.
 *
 * Steps before the current one link back to their screen (you can always go and
 * look at the evidence), the current one is marked `aria-current="step"`, and
 * steps after it are deliberately inert: they are a route forward, not a
 * shortcut to a page that has nothing in it yet.
 */
export const FLOW = [
  { key: 'insight', label: 'Insight', to: '/insights' },
  { key: 'prioritized', label: 'Prioritized', to: '/prioritization' },
  { key: 'roadmap', label: 'Roadmap', to: '/roadmap' },
  { key: 'prd', label: 'PRD', to: '/prds' },
  { key: 'stories', label: 'Stories', to: '/user-stories' },
  { key: 'measured', label: 'Measured', to: '/outcomes' },
];

export default function ProgressTrail({ current, className = '' }) {
  const index = FLOW.findIndex((step) => step.key === current);
  if (index === -1) return null;

  return (
    <nav className={['trail', className].filter(Boolean).join(' ')} aria-label="Product flow">
      <ol className="trail-list">
        {FLOW.map((step, i) => {
          const state = i < index ? 'done' : i === index ? 'current' : 'next';
          return (
            <li key={step.key} className={`trail-step is-${state}`}>
              {state === 'next' ? (
                <span className="trail-label">{step.label}</span>
              ) : (
                <Link
                  to={step.to}
                  className="trail-label"
                  aria-current={state === 'current' ? 'step' : undefined}
                >
                  {step.label}
                </Link>
              )}
              {i < FLOW.length - 1 && (
                <span className="trail-sep" aria-hidden="true">
                  <Icon name="chevronRight" size={12} />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
