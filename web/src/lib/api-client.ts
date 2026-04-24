import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '';

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

// Auto-refresh token on 401 Unauthorized
let isRefreshing = false;
let pendingRequests: Array<{ resolve: (token: string) => void; reject: (err: unknown) => void }> = [];

function onRefreshSuccess(newAccessToken: string) {
  pendingRequests.forEach(({ resolve }) => resolve(newAccessToken));
  pendingRequests = [];
}

function onRefreshFailure(err: unknown) {
  pendingRequests.forEach(({ reject }) => reject(err));
  pendingRequests = [];
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response?.status === 401 &&
      typeof window !== 'undefined' &&
      !originalRequest._retried
    ) {
      const path = window.location.pathname;
      if (path === '/login' || path === '/register') {
        return Promise.reject(error);
      }

      const refreshToken = localStorage.getItem('refresh_token');
      if (!refreshToken) {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
        return Promise.reject(error);
      }

      if (isRefreshing) {
        // Queue this request until refresh completes
        return new Promise((resolve, reject) => {
          pendingRequests.push({
            resolve: (token: string) => {
              originalRequest.headers.Authorization = `Bearer ${token}`;
              originalRequest._retried = true;
              resolve(apiClient(originalRequest));
            },
            reject: (err: unknown) => reject(err),
          });
        });
      }

      isRefreshing = true;
      originalRequest._retried = true;

      try {
        const res = await axios.post(`${BASE_URL}/api/auth/refresh`, {
          refresh_token: refreshToken,
        });
        const { access_token: newAccess, refresh_token: newRefresh } = res.data;
        localStorage.setItem('access_token', newAccess);
        localStorage.setItem('refresh_token', newRefresh);

        originalRequest.headers.Authorization = `Bearer ${newAccess}`;
        onRefreshSuccess(newAccess);
        return apiClient(originalRequest);
      } catch (refreshError) {
        onRefreshFailure(refreshError);
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
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
  getPriceHistory: (themeId: number, days: number = 60) =>
    apiClient.get<{ stocks: { stock_code: string; stock_name: string; entry_date: string; entry_price: number | null; prices: { date: string; open: number; high: number; low: number; close: number; volume: number }[] }[] }>(`/api/theme-pool/themes/${themeId}/price-history`, { params: { days } }),
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
  updateReason: (stockId: number, reason: string | null) =>
    apiClient.patch(`/api/theme-pool/stocks/${stockId}/reason`, { reason }),

  // Votes
  vote: (stockId: number, vote: number) =>
    apiClient.post<{ up_votes: number; down_votes: number; my_vote: number | null }>(`/api/theme-pool/stocks/${stockId}/vote`, { vote }),
  removeVote: (stockId: number) =>
    apiClient.delete<{ up_votes: number; down_votes: number; my_vote: number | null }>(`/api/theme-pool/stocks/${stockId}/vote`),
};

export const marketOverviewApi = {
  summary: () =>
    apiClient.get<MarketOverviewSummary>('/api/market-overview/summary'),
  dashboard: () =>
    apiClient.get<MarketDashboardData>('/api/market-overview/dashboard'),
  signalLog: (days: number = 7) =>
    apiClient.get<SignalLogEntry[]>('/api/market-overview/signal-log', { params: { days } }),
  invalidateCache: () =>
    apiClient.delete('/api/market-overview/cache'),
};

// ============================================================
// Market Dashboard types (6-section dashboard)
// ============================================================

export interface DashboardIndicator {
  value: number | string | null;
  signal?: string;
  unit?: string;
  change?: string;
  [key: string]: unknown;
}

export interface TemperatureSection {
  available: boolean;
  score?: number;
  level?: string;
  level_label?: string;
  indicators?: Record<string, DashboardIndicator>;
  volume_series?: SeriesPoint[];
  error?: string;
}

export interface TrendSection {
  available: boolean;
  level?: string;
  level_label?: string;
  indices?: Record<string, { name: string; close: number | null; change_pct: number | null }>;
  indicators?: {
    ma_position?: { above: string[]; below: string[] };
    ma_alignment?: string;
    macd_weekly?: { status: string; histogram?: string; dif?: number; dea?: number; hist?: number };
    adx?: { value: number | null; signal: string };
    svd?: { state: string; state_label: string; top1_ratio?: number; is_mutation: boolean; date?: string };
  };
  trend_series?: SeriesPoint[];
  error?: string;
}

export interface SentimentSection {
  available: boolean;
  score?: number;
  level?: string;
  level_label?: string;
  indicators?: Record<string, DashboardIndicator>;
  sentiment_series?: SeriesPoint[];
  error?: string;
}

export interface StyleSection {
  available: boolean;
  scale?: { direction: string; strength: string; label: string; strength_label: string; signals?: Record<string, number>; total?: number };
  style?: { direction: string; strength: string; label: string; strength_label: string; signals?: Record<string, number>; total?: number };
  anchor_5y?: { deviation_pct: number | null; signal: string; signal_text?: string; current?: number; ma5y?: number };
  error?: string;
}

export interface StockBondSection {
  available: boolean;
  level?: string;
  level_label?: string;
  spread?: { earnings_yield?: number; cn_bond?: number; spread_cn?: number; signal?: string; pe?: number };
  dividend?: { div_yield?: number; spread?: number; signal?: string };
  fund_rolling?: { current_pct?: number; signal?: string; signal_text?: string };
  spread_series?: SeriesPoint[];
  error?: string;
}

export interface MacroSection {
  available: boolean;
  level?: string;
  level_label?: string;
  macro_score?: number;
  indicators?: Record<string, DashboardIndicator>;
  error?: string;
}

export interface SignalLogEntry {
  date: string;
  section: string;
  from: string;
  to: string;
  detail: string;
}

export interface MarketDashboardData {
  updated_at: string;
  temperature: TemperatureSection;
  trend: TrendSection;
  sentiment: SentimentSection;
  style: StyleSection;
  stock_bond: StockBondSection;
  macro: MacroSection;
  signal_log: SignalLogEntry[];
  error?: string;
}

// ============================================================
// Positions API
// ============================================================

export interface PositionItem {
  id: number;
  stock_code: string;
  stock_name: string | null;
  level: string | null;
  shares: number | null;
  cost_price: number | null;
  account: string | null;
  note: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PositionMarketData {
  close: number | null;
  trade_date: string | null;
  close_5d?: number;
  change_5d_pct?: number;
  cost_pct?: number;
}

export interface MarketDataFreshness {
  expected_date: string;
  is_market_hours: boolean;
  is_after_close: boolean;
  data_ready: boolean;
  stale_count: number;
  total_count: number;
}

// 通用 CSV 下载工具：从后端拿 blob 并触发浏览器下载
export async function downloadCsv(path: string, params: Record<string, unknown>, filename: string) {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  const query = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') query.set(k, String(v));
  }
  const url = `${BASE_URL}${path}${query.toString() ? '?' + query.toString() : ''}`;
  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`导出失败: ${res.status}`);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(objectUrl), 100);
}

export const positionsApi = {
  list: (params?: { level?: string; active_only?: boolean }) =>
    apiClient.get<{ items: PositionItem[]; total: number }>('/api/positions', { params }),
  create: (data: { stock_code: string; stock_name?: string; level?: string; shares?: number; cost_price?: number; account?: string; note?: string }) =>
    apiClient.post<PositionItem>('/api/positions', data),
  update: (id: number, data: { stock_name?: string; level?: string; shares?: number; cost_price?: number; account?: string; note?: string }) =>
    apiClient.put<PositionItem>(`/api/positions/${id}`, data),
  remove: (id: number) =>
    apiClient.delete(`/api/positions/${id}`),
  importBatch: (items: Array<{ stock_code: string; stock_name?: string; level?: string; shares?: number; cost_price?: number; account?: string; note?: string }>) =>
    apiClient.post<{ created: number; skipped: number }>('/api/positions/import', { items }),
  marketData: () =>
    apiClient.get<Record<string, PositionMarketData>>('/api/positions/market-data'),
  marketDataFreshness: () =>
    apiClient.get<MarketDataFreshness>('/api/positions/market-data/freshness'),
  export: (params?: { level?: string; active_only?: boolean }) =>
    downloadCsv('/api/positions/export', params || {}, 'positions.csv'),
  batchAnalyze: () =>
    apiClient.post<BatchAnalyzeResult>('/api/positions/batch-analyze'),
  trade: (id: number, data: { action: 'add' | 'reduce' | 'close'; price: number; shares?: number }) =>
    apiClient.post<TradeActionResponse>(`/api/positions/${id}/trade`, data),
};

export interface TradeActionResponse {
  position_id: number;
  action: string;
  shares_before: number | null;
  shares_after: number | null;
  cost_before: number | null;
  cost_after: number | null;
  pnl_pct: number | null;
  closed: boolean;
}

export interface StockTech {
  trade_date: string;
  close: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  chg_pct: number | null;
  chg_5d_pct: number | null;
  vol_ratio: number | null;
}

export interface StockAnnouncement {
  date: string;
  type: string;
  title: string;
  direction: string;
  magnitude: string;
  summary: string;
}

export interface StockAnalysis {
  stock_code: string;
  stock_name: string;
  tech: StockTech;
  today_announcements: StockAnnouncement[];
  recent_announcements: StockAnnouncement[];
}

export interface BatchAnalyzeResult {
  stocks: StockAnalysis[];
  announcement_fetched: boolean;
}

// ============================================================
// Risk Overview API
// ============================================================

export interface RiskOverviewData {
  svd: {
    date: string;
    state: string;
    is_mutation: boolean;
    top1_ratio: number | null;
    top3_ratio: number | null;
  } | null;
  qvix: {
    date: string;
    value: number;
    level: string;
    label: string;
    suggested_exposure: number;
  } | null;
  concentration: {
    total_positions: number;
    stock_weights: { stock_code: string; stock_name: string; weight: number }[];
    max_stock: { stock_code: string; stock_name: string; weight: number } | null;
    overweight_stocks: { stock_code: string; stock_name: string; weight: number }[];
  } | null;
  sector: {
    sector_weights: { industry: string; weight: number }[];
    overweight_sectors: { industry: string; weight: number }[];
    unknown_pct: number;
  } | null;
}

export interface SvdTrendPoint {
  date: string;
  top1: number | null;
  top3: number | null;
  state: string;
  mutation: boolean;
}

export interface SvdTrendData {
  series: SvdTrendPoint[];
  window_size: number;
  days: number;
}

export const riskApi = {
  overview: () => apiClient.get<RiskOverviewData>('/api/risk/overview'),
  scan: () => apiClient.get('/api/risk/scan', { timeout: 90000 }),
  svdTrend: (params?: { days?: number; window_size?: number }) =>
    apiClient.get<SvdTrendData>('/api/risk/svd-trend', { params }),
};

// ============================================================
// Trade Operation Log API (调仓日志)
// ============================================================

export interface TradeLogItem {
  id: number;
  operation_type: string;
  stock_code: string;
  stock_name: string | null;
  detail: string | null;
  before_value: string | null;
  after_value: string | null;
  source: string;
  created_at: string;
}

export const tradeLogApi = {
  list: (params?: { operation_type?: string; from_date?: string; to_date?: string; stock_code?: string; page?: number; page_size?: number }) =>
    apiClient.get<{ items: TradeLogItem[]; total: number }>('/api/trade-logs', { params }),
  create: (data: { stock_code?: string; stock_name?: string; detail?: string }) =>
    apiClient.post<TradeLogItem>('/api/trade-logs', data),
  stats: (params?: { days?: number; stock_code?: string }) =>
    apiClient.get<{
      period_days: number;
      stock_code: string | null;
      total: number;
      by_type: Record<string, number>;
      top_stocks: { stock_code: string; stock_name: string; total: number; open: number; close: number; add_reduce: number }[];
      close_summary: { count: number; stocks: [string, string][] };
    }>('/api/trade-logs/stats', { params }),
  export: (params?: { operation_type?: string; from_date?: string; to_date?: string; stock_code?: string }) =>
    downloadCsv('/api/trade-logs/export', params || {}, 'trade_logs.csv'),
};

// ============================================================
// Inbox API
// ============================================================

export interface InboxMessageItem {
  id: number;
  message_type: string;
  title: string;
  content: string | null;
  metadata_json: string | null;
  is_read: boolean;
  created_at: string;
}

export const inboxApi = {
  list: (params?: { message_type?: string; is_read?: boolean; page?: number; page_size?: number }) =>
    apiClient.get<{ items: InboxMessageItem[]; total: number; unread_count: number }>('/api/inbox', { params }),
  get: (id: number) =>
    apiClient.get<InboxMessageItem>(`/api/inbox/${id}`),
  markRead: (id: number) =>
    apiClient.patch(`/api/inbox/${id}/read`),
  markAllRead: () =>
    apiClient.post('/api/inbox/mark-all-read'),
  remove: (id: number) =>
    apiClient.delete(`/api/inbox/${id}`),
  unreadCount: () =>
    apiClient.get<{ unread_count: number }>('/api/inbox/unread-count'),
};

// ============================================================
// User API
// ============================================================

export const userApi = {
  updateProfile: (data: { display_name?: string; email?: string }) =>
    apiClient.put('/api/auth/me', data),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiClient.post('/api/auth/change-password', { current_password: currentPassword, new_password: newPassword }),
};

// ============================================================
// Agent Assistant API
// ============================================================

export interface AgentConversationSummary {
  id: string;
  title: string;
  active_skill: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentMessageOut {
  id: number;
  role: string;
  content: string | null;
  tool_calls: unknown[] | null;
  tool_call_id: string | null;
  tool_name: string | null;
  created_at: string;
}

export interface AgentConversationDetail {
  id: string;
  title: string;
  active_skill: string | null;
  messages: AgentMessageOut[];
  created_at: string;
  updated_at: string;
}

export interface AgentToolInfo {
  name: string;
  description: string;
  category: string;
  source: string;
  min_tier: string;
}

export const agentApi = {
  listConversations: () =>
    apiClient.get<AgentConversationSummary[]>('/api/agent/conversations'),
  getConversation: (id: string) =>
    apiClient.get<AgentConversationDetail>(`/api/agent/conversations/${id}`),
  deleteConversation: (id: string) =>
    apiClient.delete(`/api/agent/conversations/${id}`),
  listTools: () =>
    apiClient.get<AgentToolInfo[]>('/api/agent/tools'),
};
