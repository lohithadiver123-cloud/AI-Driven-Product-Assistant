
import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import Icon from './Icon';
import { useBusy } from '../context/BusyContext';
import { WorkspaceSwitcher } from './ui';

/**
 * Navigation by lifecycle stage, not by screen.
 *
 * Nine flat links made the product read as nine features; the four stages below
 * make it read as one pipeline — understand, decide, build, measure — and the
 * section bar under the top bar shows only the two or three screens you are
 * currently inside. Every destination still lives here, so nothing is hidden,
 * but the bar never shows more than five things at once.
 */
const STAGES = [
  {
    id: 'understand',
    label: 'Understand',
    icon: 'bulb',
    blurb: 'What customers are telling you',
    items: [
      { to: '/dashboard', label: 'Dashboard', desc: 'What to act on first in this workspace' },
      { to: '/insights', label: 'Insights', desc: 'Pain points, themes and their evidence' },
      { to: '/feedback', label: 'Feedback', desc: 'Every review and request, searchable' },
    ],
  },
  {
    id: 'decide',
    label: 'Decide',
    icon: 'scale',
    blurb: 'What to build, and in what order',
    items: [
      { to: '/prioritization', label: 'Prioritization', desc: 'Score and rank the backlog' },
      { to: '/roadmap', label: 'Roadmap', desc: 'Releases sequenced from evidence' },
    ],
  },
  {
    id: 'build',
    label: 'Build',
    icon: 'layout',
    blurb: 'Turn decisions into specs',
    items: [
      { to: '/prds', label: 'PRD Studio', desc: 'Requirements, grounded in feedback' },
      { to: '/user-stories', label: 'User Stories', desc: 'Stories and acceptance criteria' },
    ],
  },
  {
    id: 'measure',
    label: 'Measure',
    icon: 'barChart',
    blurb: 'Whether the fix worked',
    items: [
      { to: '/outcomes', label: 'Outcomes', desc: 'Before-and-after on the metrics' },
      { to: '/reports', label: 'Reports', desc: 'Shareable summaries for stakeholders' },
    ],
  },
];

/** The stage a path belongs to. Longest prefix wins, so `/prds/:id` resolves. */
function stageOf(pathname) {
  let best = STAGES[0];
  let bestLength = -1;
  for (const stage of STAGES) {
    for (const item of stage.items) {
      if (pathname === item.to || pathname.startsWith(`${item.to}/`)) {
        if (item.to.length > bestLength) {
          best = stage;
          bestLength = item.to.length;
        }
      }
    }
  }
  return best;
}

function initials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('');
}

function UserMenu() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const user = JSON.parse(localStorage.getItem('pm_copilot_user') || 'null');

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const logout = () => {
    localStorage.removeItem('pm_copilot_token');
    localStorage.removeItem('pm_copilot_user');
    navigate('/');
  };

  return (
    <div className="navbar-user" ref={ref} style={{ position: 'relative' }}>
      <span className="navbar-username">{user?.name}</span>
      <button
        type="button"
        className="avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu for ${user?.name || 'user'}`}
        onClick={() => setOpen((v) => !v)}
      >
        {initials(user?.name)}
      </button>

      {open && (
        <div className="card menu" role="menu">
          <div className="menu-header">
            <strong>{user?.name}</strong>
            <span className="text-muted text-xs">{user?.email}</span>
          </div>
          <button
            type="button"
            className="menu-item"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              navigate('/import');
            }}
          >
            <Icon name="upload" size={15} />
            Import feedback
          </button>
          <button type="button" className="menu-item" role="menuitem" onClick={logout}>
            <Icon name="logOut" size={15} />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

/** The active stage's screens, as the second row of the shell. */
function SectionBar({ stage }) {
  return (
    <div className="section-bar">
      <div className="section-bar-inner">
        <ul className="section-tabs">
          {stage.items.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) => `section-tab${isActive ? ' is-active' : ''}`}
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
        <p className="section-bar-stage">
          <span className="section-bar-stage-label">{stage.label}</span>
          {stage.blurb}
        </p>
      </div>
    </div>
  );
}

/** The narrow-screen navigation disclosure; hidden whenever the stages fit. */
function MobileNav({ activeStage }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => {
      if (!ref.current?.contains(event.target)) setOpen(false);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="navbar-mobile" ref={ref}>
      <button
        type="button"
        className="btn btn-icon btn-subtle"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Open navigation"
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name={open ? 'x' : 'menu'} size={16} />
      </button>

      {open && (
        <div className="card menu navbar-mobile-panel" role="menu">
          {STAGES.map((stage) => (
            <div key={stage.id} className="navbar-mobile-group">
              <p className="navbar-section-header">{stage.label}</p>
              {stage.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  role="menuitem"
                  className={({ isActive }) => `menu-item${isActive ? ' is-active' : ''}`}
                  onClick={() => setOpen(false)}
                >
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </div>
      )}

      <span className="navbar-mobile-stage">{activeStage.label}</span>
    </div>
  );
}

export default function Navbar() {
  const { busy, label } = useBusy();
  const { pathname } = useLocation();
  const activeStage = stageOf(pathname);

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <NavLink to="/dashboard" className="navbar-brand">
          <span className="navbar-mark">PM</span>
          <span>Copilot</span>
        </NavLink>

        <div className="navbar-links">
          {STAGES.map((stage) => {
            const isActive = stage.id === activeStage.id;
            return (
              <NavLink
                key={stage.id}
                to={stage.items[0].to}
                className={`stage-tab${isActive ? ' is-active' : ''}`}
              >
                {stage.icon && <Icon name={stage.icon} size={15} className="stage-tab-icon" />}
                <span>{stage.label}</span>
              </NavLink>
            );
          })}
        </div>

        <div className="navbar-tools">
          <WorkspaceSwitcher className="navbar-ws" />
          <MobileNav activeStage={activeStage} />
          <UserMenu />
        </div>
      </div>

      <SectionBar stage={activeStage} />

      {busy && (
        <div className="navbar-progress" aria-live="polite">
          <div className="progress">
            <span className="progress-fill indeterminate" />
          </div>
          {label && <span className="sr-only">{label}</span>}
        </div>
      )}
    </nav>
  );
}
