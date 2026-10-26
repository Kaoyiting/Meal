const configuredBase = import.meta.env?.VITE_API_BASE_URL;
const apiBase = configuredBase || '';
const tokenKey = 'meal.accessToken';

export class ApiError extends Error {
  constructor(message, status, payload = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export function getToken() {
  return typeof localStorage === 'undefined' ? null : localStorage.getItem(tokenKey);
}

export function setToken(token) {
  if (typeof localStorage !== 'undefined') localStorage.setItem(tokenKey, token);
}

export function clearToken() {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(tokenKey);
}

function errorMessage(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  if (payload?.message) return payload.message;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).join('、');
  return `API 請求失敗（${status}）`;
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');

  const token = getToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  let response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      ...options,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError('連線不到 Meal API。請確認 FastAPI 已在 http://localhost:8000 啟動。', 0);
  }

  const text = await response.text();
  let payload = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { message: text };
    }
  }

  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/login')) {
      clearToken();
      if (typeof window !== 'undefined') window.dispatchEvent(new Event('meal:auth-expired'));
    }
    throw new ApiError(errorMessage(payload, response.status), response.status, payload);
  }
  return payload;
}

export function apiUrl(path) {
  return `${apiBase}${path}`;
}
