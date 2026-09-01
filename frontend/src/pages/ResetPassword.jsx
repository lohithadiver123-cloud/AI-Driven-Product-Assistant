import React, { useState } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { authResetPassword } from '../services/api';

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') || '';

  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const hasMinLength = newPassword.length >= 8;
  const hasLetter = /[a-zA-Z]/.test(newPassword);
  const hasNumber = /[0-9]/.test(newPassword);
  const passwordsMatch = newPassword && confirmPassword && newPassword === confirmPassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!token) {
      setError('Missing or invalid password reset token in URL.');
      return;
    }

    if (!hasMinLength || !hasLetter || !hasNumber) {
      setError('Password must be at least 8 characters and include both letters and numbers.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await authResetPassword(token, newPassword, confirmPassword);
      setSuccess(true);
      setTimeout(() => {
        navigate('/login');
      }, 2500);
    } catch (err) {
      setError(err.message || 'Password reset failed. The link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="auth-page-wrapper">
        <div className="auth-card">
          <div className="auth-brand-header">
            <span className="brand-logo-symbol">⚠️</span>
            <h1 className="auth-title">Invalid Reset Link</h1>
            <p className="auth-subtitle">
              No reset token was found in the link. Please request a new password reset.
            </p>
          </div>
          <Link to="/forgot-password" className="auth-btn-primary" style={{ display: 'block', textAlign: 'center', marginTop: '20px' }}>
            Request New Reset Link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card">
        <div className="auth-brand-header">
          <div className="brand-logo-glow">
            <span className="brand-logo-symbol">🔒</span>
          </div>
          <h1 className="auth-title">Choose New Password</h1>
          <p className="auth-subtitle">
            Enter a strong new password for your account
          </p>
        </div>

        {error && (
          <div className="auth-alert error">
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {success ? (
          <div className="auth-success-box">
            <div className="success-icon">✓</div>
            <h3>Password Reset Successful!</h3>
            <p>Your password has been updated. Redirecting to sign in...</p>
            <Link to="/login" className="auth-btn-primary" style={{ display: 'block', textAlign: 'center', marginTop: '20px' }}>
              Sign In Now
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label htmlFor="reset-new-password">New Password</label>
              <input
                id="reset-new-password"
                type="password"
                placeholder="Minimum 8 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                autoFocus
                className="auth-input"
              />
              {newPassword && (
                <div className="password-checklist">
                  <div className={`check-item ${hasMinLength ? 'valid' : 'invalid'}`}>
                    {hasMinLength ? '✓' : '○'} 8+ characters
                  </div>
                  <div className={`check-item ${hasLetter ? 'valid' : 'invalid'}`}>
                    {hasLetter ? '✓' : '○'} Includes letters
                  </div>
                  <div className={`check-item ${hasNumber ? 'valid' : 'invalid'}`}>
                    {hasNumber ? '✓' : '○'} Includes numbers
                  </div>
                </div>
              )}
            </div>

            <div className="form-group">
              <label htmlFor="reset-confirm-password">Confirm New Password</label>
              <input
                id="reset-confirm-password"
                type="password"
                placeholder="Re-enter new password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="auth-input"
              />
              {confirmPassword && (
                <div className={`password-match-hint ${passwordsMatch ? 'match' : 'no-match'}`}>
                  {passwordsMatch ? '✓ Passwords match' : '✗ Passwords do not match'}
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="auth-btn-primary"
            >
              {loading ? (
                <span className="btn-loading-flex">
                  <span className="mini-spinner"></span>
                  <span>Updating Password...</span>
                </span>
              ) : (
                'Save New Password'
              )}
            </button>
          </form>
        )}

        <div className="auth-footer-text">
          <Link to="/login" className="auth-link-highlight">
            Back to Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
