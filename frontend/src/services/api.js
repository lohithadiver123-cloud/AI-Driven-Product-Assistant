/**
 * API service layer.
 * Provides an axios instance configured with relative base URL for Vite proxy,
 * JWT token attachment from localStorage, automatic 401 handling,
 * in-memory GET caching with in-flight deduplication, and intelligent cache invalidation.
 */

import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
});

// Cache storage for instant tab transitions
const getCache = new Map();
const inFlight = new Map();

/**
 * Invalidate cached responses by URL substring or completely.
 * @param {string} [prefix] Optional substring to match in cached URLs
 */
api.invalidateCache = (prefix) => {
  if (!prefix) {
    getCache.clear();
    return;
  }
  for (const key of getCache.keys()) {
    if (key.includes(prefix)) {
      getCache.delete(key);
    }
  }
};

api.clearCache = () => {
  getCache.clear();
  inFlight.clear();
};

/**
 * Synchronously retrieve fresh cached data if available.
 * Enables instant component rendering with zero skeleton flash.
 */
api.getCached = (url, params) => {
  const cacheKey = url + (params ? JSON.stringify(params) : '');
  const cached = getCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.response.data;
  }
  return null;
};

// Request interceptor — attach JWT token to every request
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('pm_copilot_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor — handle 401 and auto-invalidate cache on mutations
api.interceptors.response.use(
  (response) => {
    const method = (response.config?.method || '').toUpperCase();
    const url = response.config?.url || '';

    // Auto-invalidate relevant cache when data is modified
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      if (url.includes('/prd')) {
        api.invalidateCache('/prd');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/user-stories')) {
        api.invalidateCache('/user-stories');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/insights')) {
        api.invalidateCache('/insights');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/prioritization')) {
        api.invalidateCache('/prioritization');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/roadmap')) {
        api.invalidateCache('/roadmap');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/feedback')) {
        api.invalidateCache('/feedback');
        api.invalidateCache('/insights');
        api.invalidateCache('/copilot/context');
      } else if (url.includes('/workspaces')) {
        api.invalidateCache('/workspaces');
      } else if (url.includes('/copilot/history')) {
        api.invalidateCache('/copilot/history');
      }
    }

    return response;
  },
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('pm_copilot_token');
      localStorage.removeItem('pm_copilot_user');
      window.location.href = '/';
    }
    return Promise.reject(error);
  }
);

// High-speed cached GET with in-flight deduplication
const originalGet = api.get.bind(api);
api.get = function (url, config = {}) {
  // Allow bypassing cache if requested
  if (config.cache === false || config.bypassCache) {
    return originalGet(url, config);
  }

  const cacheKey = url + (config.params ? JSON.stringify(config.params) : '');
  const now = Date.now();
  const cached = getCache.get(cacheKey);

  // Return immediately if cache is fresh (default 60s TTL)
  if (cached && cached.expiresAt > now) {
    return Promise.resolve({
      ...cached.response,
      data: cached.response.data,
      __fromCache: true,
    });
  }

  // Deduplicate identical in-flight requests
  if (inFlight.has(cacheKey)) {
    return inFlight.get(cacheKey);
  }

  const ttl = config.ttl || 120000;
  const promise = originalGet(url, config)
    .then((response) => {
      inFlight.delete(cacheKey);
      if (response && response.status >= 200 && response.status < 300) {
        getCache.set(cacheKey, {
          response: {
            data: response.data,
            status: response.status,
            statusText: response.statusText,
            headers: response.headers,
            config: response.config,
          },
          expiresAt: Date.now() + ttl,
        });
      }
      return response;
    })
    .catch((error) => {
      inFlight.delete(cacheKey);
      throw error;
    });

  inFlight.set(cacheKey, promise);
  return promise;
};

export default api;
