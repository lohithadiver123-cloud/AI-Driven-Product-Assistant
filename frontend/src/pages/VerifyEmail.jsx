import React, { useState, useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { authVerifyEmail, authResendVerification } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') || '';
  const { user, refreshUserProfile } = useAuth();

  const [verifying, setVerifying] = useState(false);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState('');
  const [resendEmail, setResendEmail] = useState(user?.email || '');
  const [resendMessage, setResendMessage] = useState('');

  useEffect(() => {
    if (token) {
      handleAutoVerify(token);
    }
  }, [token]);

  const handleAutoVerify = async (tokenVal) => {
    setVerifying(true);
    setError('');
    try {
      await authVerifyEmail(tokenVal);
      setVerified(true);
      if (refreshUserProfile) refreshUserProfile();
    } catch (err) {
      setError(err.message || 'Verification token is invalid or has expired.');
    } finally {
      setVerifying(false);
    }
  };

  const handleResend = async (e) => {
    e.preventDefault();
    if (!resendEmail.trim()) return;
    try {
      await authResendVerification(resendEmail.trim());
      setResendMessage(`If an unverified account exists for ${resendEmail}, a new link has been dispatched.`);
    } catch (err) {
      setError(err.message || 'Failed to resend verification link.');
    }
  };

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card">
        <div className="auth-brand-header">
          <div className="brand-logo-glow">
            <span className="brand-logo-symbol">✉️</span>
          </div>
          <h1 className="auth-title">Email Verification</h1>
          <p className="auth-subtitle">
            Confirming your AI Product Assistant account
          </p>
        </div>

        {verifying && (
          <div className="auth-loading-screen" style={{ minHeight: '120px' }}>
            <div className="spinner-orbit">
              <div className="spinner-core"></div>
            </div>
            <p className="auth-loading-text">Validating verification token...</p>
          </div>
        )}

        {verified && (
          <div className="auth-success-box">
            <div className="success-icon">✓</div>
            <h3>Email Verified Successfully!</h3>
            <p>Your email address is now confirmed. You have full access to your Product Workspace.</p>
            <Link to="/dashboard" className="auth-btn-primary" style={{ display: 'block', textAlign: 'center', marginTop: '20px' }}>
              Go to Dashboard
            </Link>
          </div>
        )}

        {error && !verified && (
          <div className="auth-alert error">
            <span className="auth-alert-icon">⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {!verified && !verifying && (
          <div className="resend-verification-section">
            <p className="subtle-note">
              Didn't receive the email or has the link expired? Enter your email address to receive a fresh verification link:
            </p>

            {resendMessage && (
              <div className="auth-alert success" style={{ marginBottom: '16px' }}>
                <span>{resendMessage}</span>
              </div>
            )}

            <form onSubmit={handleResend} className="auth-form">
              <div className="form-group">
                <input
                  type="email"
                  placeholder="your-email@company.com"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  required
                  className="auth-input"
                />
              </div>

              <button type="submit" className="auth-btn-secondary">
                Resend Verification Link
              </button>
            </form>
          </div>
        )}

        <div className="auth-footer-text">
          <Link to="/dashboard" className="auth-link-highlight">
            Continue to Workspace
          </Link>
        </div>
      </div>
    </div>
  );
}
