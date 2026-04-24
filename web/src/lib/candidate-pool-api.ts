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
