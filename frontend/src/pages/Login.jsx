import React, { useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/dashboard';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!email.trim() || !password) {
      setError('Please provide both email address and password.');
      return;
    }

    setLoading(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      setError(err.message || 'Failed to sign in. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card">
        {/* Brand Icon & Heading */}
        <div className="auth-brand-header">
          <div className="brand-logo-glow">
            <span className="brand-logo-symbol">✦</span>
          </div>
          <h1 className="auth-title">AI Product Assistant</h1>
          <p className="auth-subtitle">
            Sign in to your Product Intelligence Workspace
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="auth-alert error">
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="login-email">Email Address</label>
            <input
              id="login-email"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
              className="auth-input"
            />
          </div>

          <div className="form-group">
            <div className="label-row">
              <label htmlFor="login-password">Password</label>
              <Link to="/forgot-password" className="auth-link-subtle">
                Forgot password?
              </Link>
            </div>
            <input
              id="login-password"
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
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
                <span>Signing in...</span>
              </span>
            ) : (
              'Sign In to Workspace'
            )}
          </button>
        </form>

        {/* Footer */}
        <div className="auth-footer-text">
          <span>Don't have an account?</span>{' '}
          <Link to="/register" className="auth-link-highlight">
            Create a workspace
          </Link>
        </div>
      </div>
    </div>
  );
}
