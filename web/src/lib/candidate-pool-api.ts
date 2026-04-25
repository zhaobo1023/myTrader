import apiClient from './api-client';

export interface CandidateAddPayload {
  stock_code: string;
  stock_name: string;
  source_type: 'industry' | 'strategy' | 'manual';
  source_detail?: string;
  entry_snapshot?: Record<string, unknown>;
  memo?: string | null;
}

export interface TagItem {
  id: number;
  name: string;
  color: string;
  stock_count?: number;
}

export const candidatePoolApi = {
  list: (params?: { status?: string; source_type?: string; tag_id?: number }) =>
    apiClient.get('/api/candidate-pool/stocks', { params }),
  add: (data: CandidateAddPayload) =>
    apiClient.post('/api/candidate-pool/stocks', data),
  updateStatus: (stockCode: string, status: string) =>
    apiClient.patch(`/api/candidate-pool/stocks/${stockCode}`, { status }),
  updateMemo: (stockCode: string, memo: string) =>
    apiClient.patch(`/api/candidate-pool/stocks/${stockCode}`, { memo }),
  remove: (stockCode: string) =>
    apiClient.delete(`/api/candidate-pool/stocks/${stockCode}`),
  history: (stockCode: string, days: number = 30) =>
    apiClient.get(`/api/candidate-pool/stocks/${stockCode}/history`, { params: { days } }),
  refreshSingle: (stockCode: string) =>
    apiClient.post(`/api/candidate-pool/stocks/${stockCode}/refresh`),
  industries: () =>
    apiClient.get<{ data: string[] }>('/api/candidate-pool/industries'),
  industryStocks: (params: { industry_name: string; sort_by?: string; min_rps?: string }) =>
    apiClient.get('/api/candidate-pool/industry-stocks', { params }),
  listMemos: (stockCode: string) =>
    apiClient.get<{ data: MemoItem[] }>(`/api/candidate-pool/stocks/${stockCode}/memos`),
  addMemo: (stockCode: string, content: string) =>
    apiClient.post<MemoItem>(`/api/candidate-pool/stocks/${stockCode}/memos`, { content }),
  deleteMemo: (stockCode: string, memoId: number) =>
    apiClient.delete(`/api/candidate-pool/stocks/${stockCode}/memos/${memoId}`),
  // Tags
  listTags: () =>
    apiClient.get<{ count: number; data: TagItem[] }>('/api/candidate-pool/tags'),
  createTag: (name: string, color?: string) =>
    apiClient.post('/api/candidate-pool/tags', { name, color }),
  ensureTag: (name: string, color?: string) =>
    apiClient.post<TagItem & { action: string }>('/api/candidate-pool/tags/ensure', { name, color }),
  deleteTag: (tagId: number) =>
    apiClient.delete(`/api/candidate-pool/tags/${tagId}`),
  tagStock: (stockId: number, tagId: number) =>
    apiClient.post(`/api/candidate-pool/stocks/${stockId}/tags`, { tag_id: tagId }),
  untagStock: (stockId: number, tagId: number) =>
    apiClient.delete(`/api/candidate-pool/stocks/${stockId}/tags/${tagId}`),
};

export interface MemoItem {
  id: number;
  content: string;
  created_at: string;
}

export interface ScreenStock {
  stock_code: string;
  stock_name: string;
  province: string | null;
  city: string | null;
  industry: string | null;
  listed_date: string | null;
  main_business_short: string | null;
  close: number | null;
  rps_250: number | null;
  rps_120: number | null;
  rps_20: number | null;
  rps_slope: number | null;
  in_pool: boolean;
  trade_date: string;
}

export interface ScreenOptions {
  provinces: string[];
  industries: string[];
}

export interface ScreenParams {
  province?: string;
  industry?: string;
  keyword?: string;
  listed_years_min?: number;
  listed_years_max?: number;
  min_rps?: number;
  sort_by?: string;
  limit?: number;
}

export const screenApi = {
  options: () =>
    apiClient.get<ScreenOptions>('/api/candidate-pool/screen/options'),
  screen: (params: ScreenParams) =>
    apiClient.get<{ count: number; data: ScreenStock[] }>('/api/candidate-pool/screen', { params }),
};
