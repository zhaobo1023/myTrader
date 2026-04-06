import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8001';

const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token from localStorage to every request
apiClient.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// Redirect to login on 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;

// Types (export for use in pages)
export interface WatchlistItem {
  id: number;
  stock_code: string;
  stock_name: string;
  note?: string;
  added_at: string;
}

export interface ScanResult {
  id: number;
  stock_code: string;
  stock_name: string;
  scan_date: string;
  score: number | null;
  score_label: string | null;
  max_severity: string;
  signals: Array<{ type: string; severity: string }> | null;
  dimension_scores: Record<string, number> | null;
  notified: boolean;
  created_at: string;
}

export interface StockSearchResult {
  stock_code: string;
  stock_name: string;
  market?: string;
  industry?: string;
}

export const watchlistApi = {
  list: () => apiClient.get<{ items: WatchlistItem[]; total: number }>('/api/watchlist'),
  add: (stock_code: string, stock_name: string, note?: string) =>
    apiClient.post<WatchlistItem>('/api/watchlist', { stock_code, stock_name, note }),
  remove: (stock_code: string) =>
    apiClient.delete(`/api/watchlist/${stock_code}`),
};

export const scanResultsApi = {
  list: (params?: { scan_date?: string; severity?: string }) =>
    apiClient.get<ScanResult[]>('/api/scan-results', { params }),
};

export const marketApi = {
  search: (query: string) =>
    apiClient.get<StockSearchResult[]>('/api/market/search', { params: { query } }),
};
