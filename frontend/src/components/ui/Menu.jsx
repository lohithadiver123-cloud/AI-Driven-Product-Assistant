import { useEffect, useRef, useState } from 'react';
import Icon from '../Icon';

/**
 * The overflow menu — everything that is not the primary action.
 *
 * Pages were stacking four or five equal buttons in a row (Copy, Export, Print,
 * Delete…), which made every action look equally important. One button that
 * opens this menu keeps a single obvious next step per screen, and destructive
 * items can be marked so they read as danger rather than as a peer of Export.
 *
 * Keyboard: the trigger toggles, Escape closes and restores focus, and an
 * outside click dismisses. Items are real buttons, so Tab and Enter just work.
 */
export default function Menu({ label = 'More actions', icon = 'sliders', items = [], align = 'right', className = '' }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);

  const close = ({ focus = false } = {}) => {
    setOpen(false);
    if (focus) triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') close({ focus: true });
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!items.length) return null;

  return (
    <div className={['menu-wrap', className].filter(Boolean).join(' ')} ref={rootRef}>
      <button
        type="button"
        className="btn btn-icon"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title={label}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name={icon} size={16} />
      </button>

      {open && (
        <div className={`card menu is-${align}`} role="menu">
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              className={`menu-item${item.tone === 'danger' ? ' is-danger' : ''}`}
              disabled={item.disabled}
              title={item.hint}
              onClick={() => {
                close();
                item.onSelect?.();
              }}
            >
              {item.icon && <Icon name={item.icon} size={15} />}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
