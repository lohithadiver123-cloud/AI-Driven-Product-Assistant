import React, { useState, useRef, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import WorkspaceSettingsModal from './WorkspaceSettingsModal';
import ChangePasswordModal from './ChangePasswordModal';

export default function Navbar({
  activeTab,
  setActiveTab,
  isOnline,
  onRefresh,
  loading,
}) {
  const { user, workspaces, switchWorkspace, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [wsMenuOpen, setWsMenuOpen] = useState(false);
  const [wsModalOpen, setWsModalOpen] = useState(false);
  const [pwModalOpen, setPwModalOpen] = useState(false);

  const userMenuRef = useRef(null);
  const wsMenuRef = useRef(null);

  // Close dropdowns when clicking outside
  useEffect(() => {
    function handleClickOutside(e) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) {
        setUserMenuOpen(false);
      }
      if (wsMenuRef.current && !wsMenuRef.current.contains(e.target)) {
        setWsMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const initials = user?.name
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .toUpperCase()
        .slice(0, 2)
    : 'U';

  const role = user?.role || 'MEMBER';

  return (
    <header className="navbar-container">
      {/* Left: Brand Identity */}
      <div className="navbar-brand" onClick={() => setActiveTab('dashboard')}>
        <div className="brand-icon-wrapper">
          <div className="brand-icon">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </div>
          <div className="brand-glow"></div>
        </div>
        <div className="brand-text">
          <div className="brand-title-row">
            <h1 className="brand-title">AI Product Assistant</h1>
            <span className="brand-badge">PRO</span>
          </div>
          <span className="brand-subtitle">
            Customer Feedback Intelligence & Requirements Workspace
          </span>
        </div>
      </div>

      {/* Middle: Navigation Segmented Control */}
      <nav className="navbar-links" aria-label="Main Navigation">
        <button
          className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
          onClick={() => setActiveTab('dashboard')}
          type="button"
        >
          <svg
            className="nav-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="3" y="3" width="7" height="9" rx="1" />
            <rect x="14" y="3" width="7" height="5" rx="1" />
            <rect x="14" y="12" width="7" height="9" rx="1" />
            <rect x="3" y="16" width="7" height="5" rx="1" />
          </svg>
          <span>Dashboard</span>
        </button>

        <button
          className={`nav-tab ${activeTab === 'feedback' ? 'active' : ''}`}
          onClick={() => setActiveTab('feedback')}
          type="button"
        >
          <svg
            className="nav-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          <span>Feedback Repository</span>
        </button>

        <button
          className={`nav-tab ${activeTab === 'upload' ? 'active' : ''}`}
          onClick={() => setActiveTab('upload')}
          type="button"
        >
          <svg
            className="nav-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          <span>Import Datasets</span>
        </button>
      </nav>

      {/* Right: Workspace Switcher & User Profile Menu */}
      <div className="navbar-actions">
        {/* Connection Beacon */}
        <div
          className={`status-indicator ${isOnline ? 'online' : 'offline'}`}
          title={isOnline ? 'Backend API & MongoDB Connected' : 'Backend Offline'}
        >
          <span className="pulse-dot"></span>
          <span className="status-label">
            {isOnline ? 'Connected' : 'Offline'}
          </span>
        </div>

        {/* Refresh Action */}
        <button
          className="icon-button refresh-action-btn"
          onClick={onRefresh}
          disabled={loading}
          title="Refresh All Datasets & Stats"
          type="button"
        >
          <svg
            className={`refresh-icon ${loading ? 'spinning' : ''}`}
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
          </svg>
          <span className="btn-label">Refresh</span>
        </button>

        <div className="navbar-divider"></div>

        {/* Workspace Switcher Dropdown */}
        {user && (
          <div className="ws-dropdown-wrapper" ref={wsMenuRef}>
            <button
              className={`ws-select-btn ${wsMenuOpen ? 'active' : ''}`}
              onClick={() => setWsMenuOpen(!wsMenuOpen)}
              title="Switch Active Workspace"
              type="button"
            >
              <div className="ws-btn-icon">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                  <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                </svg>
              </div>
              <span className="ws-name-truncate">
                {user.workspace_name || 'My Workspace'}
              </span>
              <svg
                className={`dropdown-chevron ${wsMenuOpen ? 'rotated' : ''}`}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {wsMenuOpen && (
              <div className="custom-dropdown ws-dropdown-menu">
                <div className="dropdown-header">
                  <span className="dropdown-header-label">Workspaces</span>
                  <span className="dropdown-header-badge">{workspaces.length}</span>
                </div>
                <div className="dropdown-items-scroll">
                  {workspaces.map((ws) => {
                    const isSelected = ws.id === user.current_workspace_id;
                    return (
                      <button
                        key={ws.id}
                        className={`dropdown-item ws-item ${
                          isSelected ? 'selected' : ''
                        }`}
                        onClick={() => {
                          switchWorkspace(ws.id);
                          setWsMenuOpen(false);
                        }}
                        type="button"
                      >
                        <div className="ws-item-left">
                          <div className="ws-item-bullet"></div>
                          <span className="ws-item-name">{ws.name}</span>
                        </div>
                        <div className="ws-item-right">
                          <span className={`ws-item-role role-${(ws.current_user_role || 'member').toLowerCase()}`}>
                            {ws.current_user_role}
                          </span>
                          {isSelected && (
                            <svg
                              className="selected-check"
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                            >
                              <polyline points="20 6 9 17 4 12" />
                            </svg>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
                <div className="dropdown-divider"></div>
                <button
                  className="dropdown-item ws-settings-link"
                  onClick={() => {
                    setWsMenuOpen(false);
                    setWsModalOpen(true);
                  }}
                  type="button"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <circle cx="12" cy="12" r="3" />
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                  </svg>
                  <span>Workspace Settings & Members</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* User Profile Dropdown */}
        {user && (
          <div className="user-menu-wrapper" ref={userMenuRef}>
            <button
              className={`user-profile-btn ${userMenuOpen ? 'active' : ''}`}
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              title="Account Settings & Profile"
              type="button"
            >
              <div className="user-avatar-pill">{initials}</div>
              <div className="user-info-text">
                <span className="user-display-name">{user.name}</span>
                <span className={`user-role-tag role-${role.toLowerCase()}`}>
                  {role}
                </span>
              </div>
              <svg
                className={`dropdown-chevron ${userMenuOpen ? 'rotated' : ''}`}
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>

            {userMenuOpen && (
              <div className="custom-dropdown user-dropdown-menu">
                <div className="user-menu-header">
                  <div className="user-menu-avatar">{initials}</div>
                  <div className="user-menu-details">
                    <div className="user-menu-fullname">{user.name}</div>
                    <div className="user-menu-email">{user.email}</div>
                  </div>
                </div>

                <div className="dropdown-divider"></div>

                <button
                  className="dropdown-item"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setWsModalOpen(true);
                  }}
                  type="button"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                    <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                  </svg>
                  <span>Workspace Settings</span>
                </button>

                <button
                  className="dropdown-item"
                  onClick={() => {
                    setUserMenuOpen(false);
                    setPwModalOpen(true);
                  }}
                  type="button"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                  </svg>
                  <span>Change Password</span>
                </button>

                <div className="dropdown-divider"></div>

                <button
                  className="dropdown-item logout-item"
                  onClick={() => {
                    setUserMenuOpen(false);
                    logout();
                  }}
                  type="button"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                  <span>Sign Out</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      <WorkspaceSettingsModal
        isOpen={wsModalOpen}
        onClose={() => setWsModalOpen(false)}
      />
      <ChangePasswordModal
        isOpen={pwModalOpen}
        onClose={() => setPwModalOpen(false)}
      />
    </header>
  );
}
