import apiClient from './api-client';

export interface CandidateAddPayload {
  stock_code: string;
  stock_name: string;
  source_type: 'industry' | 'strategy' | 'manual';
  source_detail?: string;
  entry_snapshot?: Record<string, unknown>;
  memo?: string | null;
}

export const candidatePoolApi = {
  list: (params?: { status?: string; source_type?: string }) =>
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
  triggerMonitor: () =>
    apiClient.post('/api/candidate-pool/monitor/trigger'),
  pushFeishu: () =>
    apiClient.post('/api/candidate-pool/monitor/push'),
  industries: () =>
    apiClient.get<{ data: string[] }>('/api/candidate-pool/industries'),
  industryStocks: (params: { industry_name: string; sort_by?: string; min_rps?: string }) =>
    apiClient.get('/api/candidate-pool/industry-stocks', { params }),
};
