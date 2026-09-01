/**
 * Centralized API Client with JWT Bearer Interceptors & Auto-Refresh
 */

const API_BASE_URL = 'http://localhost:8000';
const API_V1 = `${API_BASE_URL}/api/v1`;

// Token storage keys
const ACCESS_TOKEN_KEY = 'apa_access_token';
const REFRESH_TOKEN_KEY = 'apa_refresh_token';

export function getStoredAccessToken() {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setStoredTokens(accessToken, refreshToken) {
  if (accessToken) localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearStoredTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * Enhanced fetch wrapper with auto-authorization headers and automatic 401 token refresh
 */
async function request(url, options = {}, retryOn401 = true) {
  const headers = { ...options.headers };

  const token = getStoredAccessToken();
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Set json content type if body is object / not FormData
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const config = {
    ...options,
    headers,
  };

  try {
    const res = await fetch(url, config);

    // If unauthorized, attempt refresh token rotation once
    if (res.status === 401 && retryOn401) {
      const refreshToken = getStoredRefreshToken();
      if (refreshToken) {
        try {
          const refreshRes = await fetch(`${API_V1}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
          });

          if (refreshRes.ok) {
            const data = await refreshRes.json();
            setStoredTokens(data.access_token, data.refresh_token);
            // Retry original request with new access token
            headers['Authorization'] = `Bearer ${data.access_token}`;
            return fetch(url, { ...config, headers });
          } else {
            // Refresh token expired or revoked
            clearStoredTokens();
            window.dispatchEvent(new Event('auth:unauthorized'));
          }
        } catch {
          clearStoredTokens();
          window.dispatchEvent(new Event('auth:unauthorized'));
        }
      } else {
        clearStoredTokens();
        window.dispatchEvent(new Event('auth:unauthorized'));
      }
    }

    return res;
  } catch (err) {
    console.error(`Request failed to ${url}:`, err);
    if (err.name === 'TypeError' && (err.message === 'Failed to fetch' || err.message.includes('fetch') || err.message.includes('NetworkError'))) {
      throw new Error('Unable to connect to the backend server. Please ensure the FastAPI backend is running on http://localhost:8000.');
    }
    throw err;
  }
}

// -----------------------------------------------------------------
// Health & System
// -----------------------------------------------------------------
export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
  return res.json();
}

export async function fetchDatabaseHealth() {
  const res = await fetch(`${API_BASE_URL}/health/database`);
  if (!res.ok) throw new Error(`Database health check failed: ${res.statusText}`);
  return res.json();
}

// -----------------------------------------------------------------
// Authentication Endpoints
// -----------------------------------------------------------------
export async function authLogin(email, password) {
  try {
    const res = await fetch(`${API_V1}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, device_info: 'Web Dashboard' }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Login failed. Please verify credentials.');
    }
    setStoredTokens(data.access_token, data.refresh_token);
    return data;
  } catch (err) {
    if (err.name === 'TypeError' && (err.message === 'Failed to fetch' || err.message.includes('fetch') || err.message.includes('NetworkError'))) {
      throw new Error('Unable to connect to the backend server. Please ensure the FastAPI backend is running on http://localhost:8000.');
    }
    throw err;
  }
}

export async function authRegister({ name, email, password, confirmPassword, workspaceName }) {
  try {
    const res = await fetch(`${API_V1}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        email,
        password,
        confirm_password: confirmPassword,
        workspace_name: workspaceName || undefined,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || 'Registration failed.');
    }
    setStoredTokens(data.access_token, data.refresh_token);
    return data;
  } catch (err) {
    if (err.name === 'TypeError' && (err.message === 'Failed to fetch' || err.message.includes('fetch') || err.message.includes('NetworkError'))) {
      throw new Error('Unable to connect to the backend server. Please ensure the FastAPI backend is running on http://localhost:8000.');
    }
    throw err;
  }
}

export async function authGetMe() {
  const res = await request(`${API_V1}/auth/me`);
  if (!res.ok) {
    throw new Error('Failed to fetch user profile.');
  }
  return res.json();
}

export async function authLogout() {
  const refreshToken = getStoredRefreshToken();
  if (refreshToken) {
    try {
      await fetch(`${API_V1}/auth/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (e) {
      console.warn('Logout notification error:', e);
    }
  }
  clearStoredTokens();
}

export async function authVerifyEmail(token) {
  const res = await fetch(`${API_V1}/auth/verify-email`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Email verification failed.');
  return data;
}

export async function authResendVerification(email) {
  const res = await fetch(`${API_V1}/auth/resend-verification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function authForgotPassword(email) {
  const res = await fetch(`${API_V1}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return res.json();
}

export async function authResetPassword(token, newPassword, confirmPassword) {
  const res = await fetch(`${API_V1}/auth/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      token,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Password reset failed.');
  return data;
}

export async function authChangePassword(currentPassword, newPassword, confirmPassword) {
  const res = await request(`${API_V1}/auth/change-password`, {
    method: 'POST',
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
      confirm_password: confirmPassword,
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to change password.');
  return data;
}

// -----------------------------------------------------------------
// Workspaces Endpoints
// -----------------------------------------------------------------
export async function fetchWorkspaces() {
  const res = await request(`${API_V1}/workspaces`);
  if (!res.ok) throw new Error('Failed to load workspaces.');
  return res.json();
}

export async function fetchCurrentWorkspace() {
  const res = await request(`${API_V1}/workspaces/current`);
  if (!res.ok) throw new Error('Failed to fetch active workspace details.');
  return res.json();
}

export async function createWorkspace(name) {
  const res = await request(`${API_V1}/workspaces`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to create workspace.');
  return data;
}

export async function switchWorkspace(workspaceId) {
  const res = await request(`${API_V1}/workspaces/switch/${workspaceId}`, {
    method: 'POST',
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to switch workspace.');
  return data;
}

export async function addWorkspaceMember(email, role = 'MEMBER') {
  const res = await request(`${API_V1}/workspaces/members`, {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to add workspace member.');
  return data;
}

export async function updateWorkspaceMemberRole(userId, role) {
  const res = await request(`${API_V1}/workspaces/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to update member role.');
  return data;
}

export async function removeWorkspaceMember(userId) {
  const res = await request(`${API_V1}/workspaces/members/${userId}`, {
    method: 'DELETE',
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Failed to remove member.');
  return data;
}

// -----------------------------------------------------------------
// Feedback Endpoints (Scoped to Workspace)
// -----------------------------------------------------------------
export async function fetchFeedbackStats() {
  const res = await request(`${API_V1}/feedback/stats`);
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.statusText}`);
  return res.json();
}

export async function fetchCategories() {
  const res = await request(`${API_V1}/feedback/categories`);
  if (!res.ok) throw new Error(`Failed to fetch categories: ${res.statusText}`);
  return res.json();
}

export async function fetchFeedbackList({
  page = 1,
  pageSize = 15,
  search = '',
  category = '',
  sentiment = '',
  priority = '',
  source = '',
} = {}) {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });

  if (search) params.append('search', search);
  if (category) params.append('category', category);
  if (sentiment) params.append('sentiment', sentiment);
  if (priority) params.append('priority', priority);
  if (source) params.append('source', source);

  const res = await request(`${API_V1}/feedback?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch feedback list: ${res.statusText}`);
  return res.json();
}

export async function uploadFeedbackCSV(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request(`${API_V1}/feedback/upload`, {
    method: 'POST',
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Upload failed: ${res.statusText}`);
  }
  return data;
}

export async function uploadFeedbackJSON(records) {
  const res = await request(`${API_V1}/feedback/upload-json`, {
    method: 'POST',
    body: JSON.stringify(records),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Upload failed: ${res.statusText}`);
  }
  return data;
}

export async function createFeedbackManual(payload) {
  const res = await request(`${API_V1}/feedback`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to create feedback');
  }
  return res.json();
}

export async function deleteFeedback(id) {
  const res = await request(`${API_V1}/feedback/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete feedback: ${res.statusText}`);
  return true;
}

// -----------------------------------------------------------------
// Support Tickets Endpoints (Scoped to Workspace)
// -----------------------------------------------------------------
export async function fetchSupportTicketsList({
  page = 1,
  pageSize = 15,
  search = '',
  category = '',
  priority = '',
  status = '',
  source = '',
} = {}) {
  const params = new URLSearchParams({
    page: page.toString(),
    page_size: pageSize.toString(),
  });

  if (search) params.append('search', search);
  if (category) params.append('category', category);
  if (priority) params.append('priority', priority);
  if (status) params.append('status', status);
  if (source) params.append('source', source);

  const res = await request(`${API_V1}/support-tickets?${params.toString()}`);
  if (!res.ok) throw new Error(`Failed to fetch support tickets: ${res.statusText}`);
  return res.json();
}

export async function fetchSupportTicketStats() {
  const res = await request(`${API_V1}/support-tickets/stats`);
  if (!res.ok) throw new Error(`Failed to fetch support ticket stats: ${res.statusText}`);
  return res.json();
}

export async function uploadSupportTicketsCSV(file) {
  const formData = new FormData();
  formData.append('file', file);

  const res = await request(`${API_V1}/support-tickets/upload`, {
    method: 'POST',
    body: formData,
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Upload failed: ${res.statusText}`);
  }
  return data;
}

export async function uploadSupportTicketsJSON(records) {
  const res = await request(`${API_V1}/support-tickets/upload-json`, {
    method: 'POST',
    body: JSON.stringify(records),
  });

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Upload failed: ${res.statusText}`);
  }
  return data;
}
