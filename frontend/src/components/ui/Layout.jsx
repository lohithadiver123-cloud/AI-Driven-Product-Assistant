import Icon from '../Icon';
import ProgressTrail from './ProgressTrail';

/**
 * Page-level layout primitives.
 *
 * Alignment rule for the whole app: page headers and section headers are
 * left-aligned, always. Centring is reserved for empty states and the auth
 * card. Nothing mixes the two.
 */

/**
 * One header for every screen: optional flow trail, title, one line of
 * purpose, then at most two actions on the right — a filled one that moves the
 * work forward and an outline one that exports or shares it. A third action
 * belongs behind the outlined one, not beside it.
 */
export function PageHeader({ title, icon, description, trail, actions, className = '' }) {
  return (
    <header className={['page-header', className].filter(Boolean).join(' ')}>
      <div className="page-heading">
        {trail && <ProgressTrail current={trail} />}
        <h1 className="page-title">
          {icon && (
            <span className="title-icon">
              <Icon name={icon} size={22} />
            </span>
          )}
          {title}
        </h1>
        {description && <p className="page-subtitle">{description}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  );
}

/** A titled block inside a page. Use one focal element per section. */
export function Section({ title, hint, actions, className = '', children }) {
  return (
    <section className={['section', className].filter(Boolean).join(' ')}>
      {(title || actions) && (
        <div className="section-header">
          <div className="stack stack-sm">
            {title && <h2 className="section-title">{title}</h2>}
            {hint && <p className="section-hint">{hint}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** The filter/action strip above a data surface. Left side filters, right side actions. */
export function Toolbar({ left, right, className = '', children }) {
  if (children) {
    return <div className={['toolbar', 'card', className].filter(Boolean).join(' ')}>{children}</div>;
  }
  return (
    <div className={['toolbar', 'card', className].filter(Boolean).join(' ')}>
      <div className="toolbar-left">{left}</div>
      {right && <div className="toolbar-right">{right}</div>}
    </div>
  );
}

/** Labelled control inside a toolbar — keeps every filter the same height. */
export function ToolbarField({ label, htmlFor, className = '', children }) {
  return (
    <div className={['filter-field', className].filter(Boolean).join(' ')}>
      {label && (
        <label className="field-label" htmlFor={htmlFor}>
          {label}
        </label>
      )}
      {children}
    </div>
  );
}

export default PageHeader;
