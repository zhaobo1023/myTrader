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

// [AUTH-DISABLED] 401 redirect disabled during dev — re-enable before prod
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // if (error.response?.status === 401 && typeof window !== 'undefined') {
    //   localStorage.removeItem('access_token');
    //   window.location.href = '/login';
    // }
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
    apiClient.get<{ count: number; data: StockSearchResult[] }>('/api/market/search', { params: { keyword: query } }),
};

// ============================================================
// Market Overview types
// ============================================================

export interface SeriesPoint {
  date: string;
  value?: number;
  [key: string]: number | string | null | undefined;
}

export interface SignalSection {
  available: boolean;
  last_date?: string;
  signal?: string;
  signal_text?: string;
  series?: SeriesPoint[];
  [key: string]: unknown;
}

export interface TriPrismSection {
  available: boolean;
  last_date?: string;
  signals?: { boll: number; ma5y: number; momentum40d: number };
  total?: number;
  direction?: string;
  strength?: string;
  name_a?: string;
  name_b?: string;
  series?: SeriesPoint[];
}

export interface MacroPulse {
  qvix?: { value: number | null; signal: string; signal_text: string };
  north_flow?: { today: number | null; sum_5d: number | null; signal: string };
  m2_yoy?: { value: number | null };
  pmi_mfg?: { value: number | null; signal: string; signal_text: string };
  ah_premium?: { value: number | null; signal: string; signal_text: string };
  available?: boolean;
}

export interface MarketOverviewSummary {
  updated_at: string;
  anchor_5y: SignalSection;
  stock_bond_spread: SignalSection;
  scale_rotation: TriPrismSection;
  style_rotation: TriPrismSection;
  dividend: SignalSection & {
    yield_spread?: SignalSection;
    rel_return_40d?: SignalSection;
    ah_rel_return_40d?: SignalSection;
  };
  equity_fund_rolling: SignalSection;
  macro_pulse: MacroPulse;
  market_turnover: SignalSection;
  error?: string;
}

// ============================================================
// Theme Pool types
// ============================================================

export interface ThemePoolItem {
  id: number;
  name: string;
  description: string | null;
  status: string;
  created_by: number;
  creator_email: string | null;
  stock_count: number;
  created_at: string;
  updated_at: string;
}

export interface ThemeStockScoreItem {
  score_date: string | null;
  rps_20: number | null;
  rps_60: number | null;
  rps_120: number | null;
  rps_250: number | null;
  tech_score: number | null;
  tech_signals: string | null;
  fundamental_score: number | null;
  fundamental_data: string | null;
  total_score: number | null;
  return_5d: number | null;
  return_10d: number | null;
  return_20d: number | null;
  return_60d: number | null;
}

export interface ThemeStockItem {
  id: number;
  theme_id: number;
  stock_code: string;
  stock_name: string;
  recommended_by: number;
  recommender_email: string | null;
  reason: string | null;
  entry_price: number | null;
  entry_date: string;
  human_status: string;
  note: string | null;
  added_at: string;
  latest_score: ThemeStockScoreItem | null;
  up_votes: number;
  down_votes: number;
  my_vote: number | null;
}

export const themePoolApi = {
  // Themes
  listThemes: (status?: string) =>
    apiClient.get<{ items: ThemePoolItem[]; total: number }>('/api/theme-pool/themes', { params: status ? { status } : {} }),
  getTheme: (id: number) =>
    apiClient.get<ThemePoolItem>(`/api/theme-pool/themes/${id}`),
  createTheme: (name: string, description?: string) =>
    apiClient.post<ThemePoolItem>('/api/theme-pool/themes', { name, description }),
  updateTheme: (id: number, data: { name?: string; description?: string }) =>
    apiClient.put<ThemePoolItem>(`/api/theme-pool/themes/${id}`, data),
  changeStatus: (id: number, status: string) =>
    apiClient.patch<ThemePoolItem>(`/api/theme-pool/themes/${id}/status`, { status }),
  deleteTheme: (id: number) =>
    apiClient.delete(`/api/theme-pool/themes/${id}`),

  // Scoring
  triggerScore: (themeId: number) =>
    apiClient.post<{ message: string; theme_id: number }>(`/api/theme-pool/themes/${themeId}/score`),

  // Stocks
  listStocks: (themeId: number, params?: { human_status?: string; sort_by?: string }) =>
    apiClient.get<{ items: ThemeStockItem[]; total: number }>(`/api/theme-pool/themes/${themeId}/stocks`, { params }),
  addStock: (themeId: number, stock_code: string, stock_name: string, reason?: string) =>
    apiClient.post<ThemeStockItem>(`/api/theme-pool/themes/${themeId}/stocks`, { stock_code, stock_name, reason }),
  batchAddStocks: (themeId: number, stocks: Array<{ stock_code: string; stock_name: string; reason?: string }>) =>
    apiClient.post<{ items: ThemeStockItem[]; total: number }>(`/api/theme-pool/themes/${themeId}/stocks/batch`, { stocks }),
  removeStock: (themeId: number, stockCode: string) =>
    apiClient.delete(`/api/theme-pool/themes/${themeId}/stocks/${stockCode}`),
  updateHumanStatus: (stockId: number, human_status: string) =>
    apiClient.patch(`/api/theme-pool/stocks/${stockId}/status`, { human_status }),
  updateNote: (stockId: number, note: string | null) =>
    apiClient.patch(`/api/theme-pool/stocks/${stockId}/note`, { note }),

  // Votes
  vote: (stockId: number, vote: number) =>
    apiClient.post<{ up_votes: number; down_votes: number; my_vote: number | null }>(`/api/theme-pool/stocks/${stockId}/vote`, { vote }),
  removeVote: (stockId: number) =>
    apiClient.delete<{ up_votes: number; down_votes: number; my_vote: number | null }>(`/api/theme-pool/stocks/${stockId}/vote`),
};

export const marketOverviewApi = {
  summary: () =>
    apiClient.get<MarketOverviewSummary>('/api/market-overview/summary'),
  invalidateCache: () =>
    apiClient.delete('/api/market-overview/cache'),
};
