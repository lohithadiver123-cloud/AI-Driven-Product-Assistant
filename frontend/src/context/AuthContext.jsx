import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import {
  authLogin,
  authRegister,
  authLogout,
  authGetMe,
  fetchWorkspaces,
  switchWorkspace as apiSwitchWorkspace,
  getStoredAccessToken,
  clearStoredTokens,
} from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(null);

  // Restore authenticated session on startup
  const restoreSession = useCallback(async () => {
    const token = getStoredAccessToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }

    try {
      const profile = await authGetMe();
      setUser(profile);
      // Fetch workspaces
      try {
        const wsList = await fetchWorkspaces();
        setWorkspaces(wsList);
      } catch (err) {
        console.warn('Could not load workspaces list:', err);
      }
    } catch (err) {
      console.warn('Session restoration failed:', err);
      clearStoredTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    restoreSession();

    // Listen for global unauthorized events (e.g. invalid refresh token)
    const handleUnauthorized = () => {
      setUser(null);
      setWorkspaces([]);
    };
    window.addEventListener('auth:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
  }, [restoreSession]);

  // Login handler
  const login = async (email, password) => {
    setAuthError(null);
    try {
      const data = await authLogin(email, password);
      setUser(data.user);
      try {
        const wsList = await fetchWorkspaces();
        setWorkspaces(wsList);
      } catch (e) {
        console.warn(e);
      }
      return data.user;
    } catch (err) {
      setAuthError(err.message);
      throw err;
    }
  };

  // Register handler
  const register = async (regData) => {
    setAuthError(null);
    try {
      const data = await authRegister(regData);
      setUser(data.user);
      try {
        const wsList = await fetchWorkspaces();
        setWorkspaces(wsList);
      } catch (e) {
        console.warn(e);
      }
      return data.user;
    } catch (err) {
      setAuthError(err.message);
      throw err;
    }
  };

  // Logout handler
  const logout = async () => {
    try {
      await authLogout();
    } catch (e) {
      console.warn(e);
    } finally {
      setUser(null);
      setWorkspaces([]);
    }
  };

  // Switch workspace
  const switchWorkspace = async (workspaceId) => {
    try {
      await apiSwitchWorkspace(workspaceId);
      const profile = await authGetMe();
      setUser(profile);
      const wsList = await fetchWorkspaces();
      setWorkspaces(wsList);
    } catch (err) {
      console.error('Failed to switch workspace:', err);
      throw err;
    }
  };

  // Refresh profile
  const refreshUserProfile = async () => {
    try {
      const profile = await authGetMe();
      setUser(profile);
      const wsList = await fetchWorkspaces();
      setWorkspaces(wsList);
    } catch (e) {
      console.warn(e);
    }
  };

  const value = {
    user,
    workspaces,
    isAuthenticated: !!user,
    loading,
    authError,
    setAuthError,
    login,
    register,
    logout,
    switchWorkspace,
    refreshUserProfile,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
