import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { authForgotPassword } from '../services/api';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!email.trim()) {
      setError('Please enter your email address.');
      return;
    }

    setLoading(true);
    try {
      await authForgotPassword(email.trim());
      setSubmitted(true);
    } catch (err) {
      setError(err.message || 'Failed to send reset link. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card">
        <div className="auth-brand-header">
          <div className="brand-logo-glow">
            <span className="brand-logo-symbol">🔑</span>
          </div>
          <h1 className="auth-title">Reset Password</h1>
          <p className="auth-subtitle">
            Enter your account email to receive a password reset link
          </p>
        </div>

        {error && (
          <div className="auth-alert error">
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {submitted ? (
          <div className="auth-success-box">
            <div className="success-icon">✉️</div>
            <h3>Check your email</h3>
            <p>
              If an account is associated with <strong>{email}</strong>, we have dispatched a single-use password reset link.
            </p>
            <p className="subtle-note">
              The link will expire in 30 minutes. Please check your inbox or spam folder.
            </p>
            <Link to="/login" className="auth-btn-primary" style={{ display: 'block', textAlign: 'center', marginTop: '20px' }}>
              Return to Sign In
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <label htmlFor="forgot-email">Account Email Address</label>
              <input
                id="forgot-email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                className="auth-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="auth-btn-primary"
            >
              {loading ? (
                <span className="btn-loading-flex">
                  <span className="mini-spinner"></span>
                  <span>Sending Reset Link...</span>
                </span>
              ) : (
                'Send Password Reset Link'
              )}
            </button>
          </form>
        )}

        <div className="auth-footer-text">
          <span>Remembered your password?</span>{' '}
          <Link to="/login" className="auth-link-highlight">
            Back to Sign In
          </Link>
        </div>
      </div>
    </div>
  );
}
