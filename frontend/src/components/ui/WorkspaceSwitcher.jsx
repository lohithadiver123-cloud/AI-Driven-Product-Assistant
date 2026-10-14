import { useEffect, useId, useRef, useState } from 'react';
import Icon from '../Icon';
import { useWorkspaces } from '../../context/WorkspaceContext';

/**
 * The workspace picker — one control, used by every screen.
 *
 * Replaces the native `<select>` each page used to ship its own copy of. It
 * reads the shared selection, so choosing an option here re-renders the whole
 * app; `onChange` exists only for screens that must reset local filters when
 * the workspace moves.
 *
 * `layout="inline"` is the pill for header actions; `layout="stacked"` puts
 * the label above a full-width trigger so it sits beside the kit's `Select`s
 * in a toolbar without looking bolted on.
 *
 * Keyboard: the trigger and every option are real buttons, so Tab and Enter
 * work for free; Escape closes and returns focus to the trigger.
 */
export default function WorkspaceSwitcher({
  label = 'Workspace',
  layout = 'inline',
  id,
  disabled = false,
  className = '',
  onChange,
}) {
  const { workspaces, activeId, activeWorkspace, loading, ready, setActive, createWorkspace } = useWorkspaces();
  const [open, setOpen] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [createError, setCreateError] = useState('');
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const inputRef = useRef(null);
  const generatedId = useId();
  const triggerId = id || generatedId;
  const listId = `${triggerId}-list`;

  const close = () => {
    setOpen(false);
    setIsCreating(false);
    setNewName('');
    setCreateError('');
    triggerRef.current?.focus();
  };

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) close();
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') close();
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const choose = (nextId) => {
    if (!nextId || nextId === activeId) {
      close();
      return;
    }
    setActive(nextId);
    onChange?.(nextId);
    close();
  };

  const handleCreate = async (e) => {
    e?.preventDefault();
    const trimmed = newName.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setCreateError('');
    try {
      const created = await createWorkspace(trimmed);
      setIsCreating(false);
      setNewName('');
      setOpen(false);
      const newId = created?._id || created?.id;
      if (newId) onChange?.(newId);
    } catch (err) {
      setCreateError(err?.response?.data?.detail || 'Failed to create workspace');
    } finally {
      setSubmitting(false);
    }
  };

  const currentName = loading
    ? 'Loading…'
    : activeWorkspace?.name || activeWorkspace?.title || 'No workspace yet';

  return (
    <div
      ref={rootRef}
      className={[
        'ws-switcher',
        layout === 'stacked' && 'is-stacked',
        open && 'is-open',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {label && (
        <label className={layout === 'stacked' ? 'field-label' : 'ws-switcher-label'} htmlFor={triggerId}>
          {label}
        </label>
      )}

      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        className="ws-trigger"
        disabled={disabled || loading}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => {
          setOpen((value) => {
            if (!value) {
              setIsCreating(false);
              setNewName('');
              setCreateError('');
            }
            return !value;
          });
        }}
      >
        <span className="ws-trigger-dot" aria-hidden="true" />
        <span className="ws-trigger-name">{currentName}</span>
        <Icon name="chevronDown" size={14} className={`ws-trigger-caret${open ? ' is-open' : ''}`} />
      </button>

      {open && (
        <div className="ws-menu" role="listbox" id={listId} aria-label={label || 'Workspaces'}>
          <div className="ws-menu-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>Workspaces</span>
              <span className="ws-menu-count">{workspaces.length}</span>
            </div>
            {!isCreating && (
              <button
                type="button"
                className="ws-head-create-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  setIsCreating(true);
                  setCreateError('');
                  setTimeout(() => inputRef.current?.focus(), 60);
                }}
              >
                <Icon name="plus" size={12} />
                <span>New</span>
              </button>
            )}
          </div>

          {isCreating && (
            <div className="ws-top-form-wrap">
              <form
                className="ws-create-form"
                onSubmit={handleCreate}
                onClick={(e) => e.stopPropagation()}
              >
                <input
                  ref={inputRef}
                  type="text"
                  className="ws-create-input"
                  placeholder="Workspace name..."
                  value={newName}
                  onChange={(e) => {
                    setNewName(e.target.value);
                    if (createError) setCreateError('');
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      setIsCreating(false);
                      setNewName('');
                      setCreateError('');
                    }
                  }}
                  disabled={submitting}
                  maxLength={60}
                  autoFocus
                />
                {createError && <p className="ws-create-error">{createError}</p>}
                <div className="ws-create-actions">
                  <button
                    type="button"
                    className="ws-btn-ghost"
                    disabled={submitting}
                    onClick={() => {
                      setIsCreating(false);
                      setNewName('');
                      setCreateError('');
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="ws-btn-primary"
                    disabled={submitting || !newName.trim()}
                  >
                    {submitting ? 'Creating…' : 'Create'}
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="ws-menu-list">
            {workspaces.length === 0 && (
              <p className="ws-menu-empty">
                {ready ? 'No workspaces yet. Create your first one above.' : 'Loading workspaces…'}
              </p>
            )}
            {workspaces.map((workspace) => {
              const wsId = workspace._id || workspace.id;
              const isActive = wsId === activeId;
              return (
                <button
                  key={wsId}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  className={`ws-option${isActive ? ' is-active' : ''}`}
                  onClick={() => choose(wsId)}
                >
                  <span className="ws-option-name">{workspace.name || 'Untitled workspace'}</span>
                  {isActive ? (
                    <Icon name="check" size={14} />
                  ) : (
                    <Icon name="chevronRight" size={14} className="ws-option-arrow" />
                  )}
                </button>
              );
            })}
          </div>

          {!isCreating && (
            <div className="ws-menu-actions">
              <button
                type="button"
                className="ws-new-btn"
                onClick={() => {
                  setIsCreating(true);
                  setCreateError('');
                  setTimeout(() => inputRef.current?.focus(), 60);
                }}
              >
                <Icon name="plus" size={13} />
                <span>New workspace</span>
              </button>
            </div>
          )}

          <p className="ws-menu-foot">Switching here updates every page.</p>
        </div>
      )}
    </div>
  );
}
