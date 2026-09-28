import axios from 'axios';

const TOKEN_KEY = 'vb.token';

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  // Returns false when the browser blocks storage, so sign-in can say so instead of
  // silently bouncing back to the login page (sara L6).
  set: (t) => { try { localStorage.setItem(TOKEN_KEY, t); return true; } catch { return false; } },
  clear: () => { try { localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } },
};

// One axios client. The interceptor attaches the Bearer token (scaffold §1); a 401 clears it
// and returns to login — never shown as an error (playbook §7).
export const http = axios.create({ baseURL: '/' });

http.interceptors.request.use((cfg) => {
  const token = tokenStore.get();
  if (token) cfg.headers.Authorization = `Bearer ${token}`;
  return cfg;
});

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401 && !err.config?.url?.endsWith('/auth/login')) {
      tokenStore.clear();
      if (window.location.pathname !== '/login') window.location.assign('/login');
    }
    return Promise.reject(err);
  },
);

export const errorText = (err, fallback = 'Something went wrong.') =>
  err?.response?.data?.detail && typeof err.response.data.detail === 'string'
    ? err.response.data.detail
    : fallback;

export const isConflict = (err) => err?.response?.status === 409;
