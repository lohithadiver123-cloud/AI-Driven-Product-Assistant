import React, { useState, useEffect } from 'react';
import { authChangePassword } from '../services/api';

export default function ChangePasswordModal({ isOpen, onClose, onPasswordChanged }) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrent, setShowCurrent] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Reset fields when opened/closed
  useEffect(() => {
    if (isOpen) {
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setError('');
      setSuccess(false);
      setShowCurrent(false);
      setShowNew(false);
      setShowConfirm(false);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  // Validation rules
  const hasMinLength = newPassword.length >= 8;
  const hasLetter = /[a-zA-Z]/.test(newPassword);
  const hasNumber = /[0-9]/.test(newPassword);
  const passwordsMatch = newPassword && confirmPassword && newPassword === confirmPassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!currentPassword) {
      setError('Please enter your current password.');
      return;
    }

    if (!hasMinLength || !hasLetter || !hasNumber) {
      setError('New password must be at least 8 characters long and contain both letters and numbers.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('New passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await authChangePassword(currentPassword, newPassword, confirmPassword);
      setSuccess(true);
      setTimeout(() => {
        onClose();
        if (onPasswordChanged) onPasswordChanged();
      }, 1600);
    } catch (err) {
      setError(err.message || 'Failed to change password. Please verify your current password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content glass-card password-modal-container"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: '460px' }}
      >
        {/* Header with security icon badge */}
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '10px',
                background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                boxShadow: '0 0 16px rgba(99, 102, 241, 0.4)',
              }}
            >
              🔐
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', color: '#f8fafc' }}>
                Change Password
              </h3>
              <p style={{ margin: '2px 0 0', fontSize: '0.78rem', color: '#94a3b8' }}>
                Update your account password securely
              </p>
            </div>
          </div>
          <button className="close-btn" onClick={onClose} title="Close (Esc)">
            &times;
          </button>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="auth-alert error" style={{ margin: '14px 0' }}>
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* Success State */}
        {success ? (
          <div className="auth-success-box" style={{ padding: '24px 0', textAlign: 'center' }}>
            <div className="success-icon" style={{ fontSize: '28px', marginBottom: '12px' }}>
              ✓
            </div>
            <h4 style={{ color: '#10b981', fontSize: '1.2rem', margin: '0 0 6px' }}>
              Password Updated Successfully!
            </h4>
            <p className="subtle-note" style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
              Your new credentials are now active across your workspace.
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="auth-form" style={{ marginTop: '14px' }}>
            {/* Current Password Field */}
            <div className="form-group">
              <label htmlFor="current-pw" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0' }}>
                Current Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="current-pw"
                  type={showCurrent ? 'text' : 'password'}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                  autoFocus
                  className="auth-input"
                  placeholder="Enter current password"
                  style={{ paddingRight: '42px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowCurrent(!showCurrent)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    fontSize: '14px',
                    padding: '4px',
                  }}
                  title={showCurrent ? 'Hide password' : 'Show password'}
                >
                  {showCurrent ? '👁️' : '👁️‍🗨️'}
                </button>
              </div>
            </div>

            {/* New Password Field */}
            <div className="form-group">
              <label htmlFor="new-pw" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0' }}>
                New Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="new-pw"
                  type={showNew ? 'text' : 'password'}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                  className="auth-input"
                  placeholder="Minimum 8 characters"
                  style={{ paddingRight: '42px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowNew(!showNew)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    fontSize: '14px',
                    padding: '4px',
                  }}
                  title={showNew ? 'Hide password' : 'Show password'}
                >
                  {showNew ? '👁️' : '👁️‍🗨️'}
                </button>
              </div>

              {/* Password Requirements Checklist */}
              {newPassword && (
                <div className="password-checklist" style={{ marginTop: '8px', display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                  <span className={`check-item ${hasMinLength ? 'valid' : 'invalid'}`}>
                    {hasMinLength ? '✓' : '○'} 8+ chars
                  </span>
                  <span className={`check-item ${hasLetter ? 'valid' : 'invalid'}`}>
                    {hasLetter ? '✓' : '○'} Letters
                  </span>
                  <span className={`check-item ${hasNumber ? 'valid' : 'invalid'}`}>
                    {hasNumber ? '✓' : '○'} Numbers
                  </span>
                </div>
              )}
            </div>

            {/* Confirm New Password Field */}
            <div className="form-group">
              <label htmlFor="confirm-pw" style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e2e8f0' }}>
                Confirm New Password
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  id="confirm-pw"
                  type={showConfirm ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className="auth-input"
                  placeholder="Re-enter new password"
                  style={{ paddingRight: '42px' }}
                />
                <button
                  type="button"
                  onClick={() => setShowConfirm(!showConfirm)}
                  style={{
                    position: 'absolute',
                    right: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    background: 'transparent',
                    border: 'none',
                    color: '#94a3b8',
                    cursor: 'pointer',
                    fontSize: '14px',
                    padding: '4px',
                  }}
                  title={showConfirm ? 'Hide password' : 'Show password'}
                >
                  {showConfirm ? '👁️' : '👁️‍🗨️'}
                </button>
              </div>

              {confirmPassword && (
                <div
                  className={`password-match-hint ${passwordsMatch ? 'match' : 'no-match'}`}
                  style={{ marginTop: '6px', fontSize: '0.78rem' }}
                >
                  {passwordsMatch ? '✓ Passwords match' : '✗ Passwords do not match'}
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="modal-actions">
              <button
                type="button"
                onClick={onClose}
                className="auth-btn-secondary"
                style={{ flex: 1 }}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading || !currentPassword || !passwordsMatch || !hasMinLength || !hasLetter || !hasNumber}
                className="auth-btn-primary"
                style={{ flex: 1 }}
              >
                {loading ? (
                  <span className="btn-loading-flex">
                    <span className="mini-spinner"></span>
                    <span>Updating...</span>
                  </span>
                ) : (
                  'Update Password'
                )}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
