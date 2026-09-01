import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Password strength helper
  const hasMinLength = password.length >= 8;
  const hasLetter = /[a-zA-Z]/.test(password);
  const hasNumber = /[0-9]/.test(password);
  const passwordsMatch = password && confirmPassword && password === confirmPassword;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!name.trim()) {
      setError('Please enter your full name.');
      return;
    }

    if (!hasMinLength || !hasLetter || !hasNumber) {
      setError('Password must be at least 8 characters and contain both letters and numbers.');
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    setLoading(true);
    try {
      await register({
        name: name.trim(),
        email: email.trim(),
        password,
        confirmPassword,
        workspaceName: workspaceName.trim() || undefined,
      });
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err.message || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card register-card">
        {/* Brand Header */}
        <div className="auth-brand-header">
          <div className="brand-logo-glow">
            <span className="brand-logo-symbol">✦</span>
          </div>
          <h1 className="auth-title">Create your Workspace</h1>
          <p className="auth-subtitle">
            Set up AI Product Assistant for your team
          </p>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="auth-alert error">
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="auth-form">
          <div className="form-group">
            <label htmlFor="reg-name">Full Name</label>
            <input
              id="reg-name"
              type="text"
              placeholder="e.g. Sarah Connor"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              className="auth-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-email">Work Email</label>
            <input
              id="reg-email"
              type="email"
              placeholder="sarah@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="auth-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-workspace">Workspace Name</label>
            <input
              id="reg-workspace"
              type="text"
              placeholder="e.g. Acme Product Hub (Optional)"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              className="auth-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-password">Password</label>
            <input
              id="reg-password"
              type="password"
              placeholder="Minimum 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="auth-input"
            />
            {/* Password Validation Checklist */}
            {password && (
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
            <label htmlFor="reg-confirm-password">Confirm Password</label>
            <input
              id="reg-confirm-password"
              type="password"
              placeholder="Re-enter password"
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
                <span>Creating Workspace...</span>
              </span>
            ) : (
              'Create Workspace'
            )}
          </button>
        </form>

        {/* Footer */}
        <div className="auth-footer-text">
          <span>Already have an account?</span>{' '}
          <Link to="/login" className="auth-link-highlight">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
