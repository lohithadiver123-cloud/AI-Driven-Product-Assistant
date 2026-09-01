import React, { useState, useEffect } from 'react';
import {
  fetchCurrentWorkspace,
  addWorkspaceMember,
  updateWorkspaceMemberRole,
  removeWorkspaceMember,
  createWorkspace,
} from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function WorkspaceSettingsModal({ isOpen, onClose }) {
  const { user, refreshUserProfile } = useAuth();
  const [workspace, setWorkspace] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('members'); // 'members' | 'create_ws'

  // Invite state
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('MEMBER');
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteMsg, setInviteMsg] = useState({ type: '', text: '' });

  // Create new workspace state
  const [newWsName, setNewWsName] = useState('');
  const [createLoading, setCreateLoading] = useState(false);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      loadWorkspace();
      setInviteMsg({ type: '', text: '' });
    }
  }, [isOpen]);

  const loadWorkspace = async () => {
    setLoading(true);
    try {
      const data = await fetchCurrentWorkspace();
      setWorkspace(data);
    } catch (err) {
      console.error('Failed to load workspace:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleInvite = async (e) => {
    e.preventDefault();
    if (!inviteEmail.trim()) return;
    setInviteLoading(true);
    setInviteMsg({ type: '', text: '' });

    try {
      const res = await addWorkspaceMember(inviteEmail.trim(), inviteRole);
      setInviteMsg({ type: 'success', text: res.message });
      setInviteEmail('');
      loadWorkspace();
    } catch (err) {
      setInviteMsg({ type: 'error', text: err.message || 'Failed to add member.' });
    } finally {
      setInviteLoading(false);
    }
  };

  const handleRoleChange = async (memberId, newRole) => {
    try {
      await updateWorkspaceMemberRole(memberId, newRole);
      loadWorkspace();
    } catch (err) {
      alert(err.message || 'Failed to update member role.');
    }
  };

  const handleRemoveMember = async (memberId) => {
    if (!window.confirm('Are you sure you want to remove this member from the workspace?')) return;
    try {
      await removeWorkspaceMember(memberId);
      loadWorkspace();
    } catch (err) {
      alert(err.message || 'Failed to remove member.');
    }
  };

  const handleCreateWorkspace = async (e) => {
    e.preventDefault();
    if (!newWsName.trim()) return;
    setCreateLoading(true);
    try {
      await createWorkspace(newWsName.trim());
      setNewWsName('');
      await refreshUserProfile();
      loadWorkspace();
      setActiveTab('members');
      setInviteMsg({ type: 'success', text: 'New workspace created and activated!' });
    } catch (err) {
      setInviteMsg({ type: 'error', text: err.message || 'Failed to create workspace.' });
    } finally {
      setCreateLoading(false);
    }
  };

  if (!isOpen) return null;

  const isOwnerOrAdmin = workspace?.current_user_role === 'OWNER' || workspace?.current_user_role === 'ADMIN';
  const isOwner = workspace?.current_user_role === 'OWNER';

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content glass-card workspace-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '680px' }}
      >
        {/* Header */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #6366f1, #06b6d4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                boxShadow: '0 0 16px rgba(99, 102, 241, 0.4)',
              }}
            >
              🏢
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.2rem', color: '#f8fafc' }}>
                Workspace Settings
              </h3>
              <p style={{ margin: '2px 0 0', fontSize: '0.8rem', color: '#94a3b8' }}>
                {workspace?.name || 'My Workspace'} &bull; {workspace?.members?.length || 1} Team Member{(workspace?.members?.length || 1) !== 1 ? 's' : ''}
              </p>
            </div>
          </div>
          <button className="close-btn" onClick={onClose} title="Close (Esc)">
            &times;
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="ws-tab-row">
          <button
            className={`ws-tab-btn ${activeTab === 'members' ? 'active' : ''}`}
            onClick={() => setActiveTab('members')}
            type="button"
          >
            👥 Team Members ({workspace?.members?.length || 0})
          </button>
          <button
            className={`ws-tab-btn ${activeTab === 'create_ws' ? 'active' : ''}`}
            onClick={() => setActiveTab('create_ws')}
            type="button"
          >
            ➕ Create New Workspace
          </button>
        </div>

        {/* Alert Messages */}
        {inviteMsg.text && (
          <div className={`auth-alert ${inviteMsg.type}`} style={{ margin: '16px 0' }}>
            <span>{inviteMsg.text}</span>
          </div>
        )}

        {/* Tab 1: Team Members */}
        {activeTab === 'members' && (
          <div className="ws-tab-content" style={{ marginTop: '16px' }}>
            {/* Professional Add Member Form */}
            {isOwnerOrAdmin && (
              <form onSubmit={handleInvite} className="invite-member-form">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <span style={{ fontSize: '15px' }}>✉️</span>
                  <label htmlFor="invite-email-input" style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f1f5f9' }}>
                    Add Team Member to Workspace
                  </label>
                </div>
                <div className="invite-inputs-grid">
                  <div style={{ position: 'relative', width: '100%' }}>
                    <input
                      id="invite-email-input"
                      type="email"
                      placeholder="Enter colleague's email address (e.g. teammate@company.com)"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      required
                      className="auth-input invite-email-field"
                    />
                  </div>

                  <select
                    value={inviteRole}
                    onChange={(e) => setInviteRole(e.target.value)}
                    className="auth-input invite-role-select"
                  >
                    <option value="MEMBER">Member (Full Access)</option>
                    <option value="ADMIN">Admin (Manage Team)</option>
                    <option value="VIEWER">Viewer (Read Only)</option>
                  </select>

                  <button
                    type="submit"
                    disabled={inviteLoading || !inviteEmail.trim()}
                    className="auth-btn-primary invite-submit-btn"
                  >
                    {inviteLoading ? (
                      <span className="btn-loading-flex">
                        <span className="mini-spinner"></span>
                        <span>Adding...</span>
                      </span>
                    ) : (
                      '+ Add Member'
                    )}
                  </button>
                </div>
              </form>
            )}

            {/* Members List Table */}
            <div className="members-list-table-container">
              <table className="custom-table">
                <thead>
                  <tr>
                    <th style={{ width: '45%' }}>Team Member</th>
                    <th style={{ width: '22%' }}>Role</th>
                    <th style={{ width: '20%' }}>Joined Date</th>
                    {isOwner && <th style={{ width: '13%', textAlign: 'right' }}>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {workspace?.members?.map((m) => (
                    <tr key={m.user_id}>
                      <td>
                        <div className="user-cell-flex">
                          <span className="avatar-dot">
                            {m.name ? m.name.charAt(0).toUpperCase() : 'U'}
                          </span>
                          <div>
                            <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.88rem' }}>
                              {m.name || 'Team Member'} {m.user_id === user?.id && <span style={{ color: '#818cf8', fontSize: '0.75rem' }}>(You)</span>}
                            </div>
                            <div style={{ fontSize: '0.78rem', color: '#94a3b8' }}>{m.email || '—'}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        {isOwner && m.role !== 'OWNER' ? (
                          <select
                            value={m.role}
                            onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                            className="role-pill-select"
                          >
                            <option value="ADMIN">ADMIN</option>
                            <option value="MEMBER">MEMBER</option>
                            <option value="VIEWER">VIEWER</option>
                          </select>
                        ) : (
                          <span className={`role-badge role-${m.role.toLowerCase()}`}>{m.role}</span>
                        )}
                      </td>
                      <td style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
                        {m.joined_at ? new Date(m.joined_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}
                      </td>
                      {isOwner && (
                        <td style={{ textAlign: 'right' }}>
                          {m.role !== 'OWNER' && (
                            <button
                              className="delete-btn-subtle"
                              onClick={() => handleRemoveMember(m.user_id)}
                              title="Remove Member from Workspace"
                            >
                              ✕ Remove
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 2: Create New Workspace */}
        {activeTab === 'create_ws' && (
          <div className="ws-tab-content" style={{ marginTop: '16px' }}>
            <div style={{
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              borderRadius: '12px',
              padding: '20px'
            }}>
              <h4 style={{ margin: '0 0 6px 0', fontSize: '1rem', color: '#f8fafc' }}>
                Create a New Isolated Workspace
              </h4>
              <p style={{ margin: '0 0 16px 0', fontSize: '0.82rem', color: '#94a3b8', lineHeight: 1.45 }}>
                Each workspace has its own independent datasets, feedback signals, members, and AI roadmap intelligence.
              </p>
              <form onSubmit={handleCreateWorkspace} className="auth-form">
                <div className="form-group">
                  <label htmlFor="new-ws-name" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0' }}>
                    Workspace Name
                  </label>
                  <input
                    id="new-ws-name"
                    type="text"
                    placeholder="e.g. Enterprise Mobile Apps Hub"
                    value={newWsName}
                    onChange={(e) => setNewWsName(e.target.value)}
                    required
                    className="auth-input"
                  />
                </div>
                <button
                  type="submit"
                  disabled={createLoading || !newWsName.trim()}
                  className="auth-btn-primary"
                  style={{ marginTop: '8px' }}
                >
                  {createLoading ? (
                    <span className="btn-loading-flex">
                      <span className="mini-spinner"></span>
                      <span>Creating Workspace...</span>
                    </span>
                  ) : (
                    'Create & Switch to Workspace'
                  )}
                </button>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
