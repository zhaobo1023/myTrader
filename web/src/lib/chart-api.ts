import apiClient from './api-client';

export interface KLineDataPoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  amount: number;
  turnover_rate: number;
  ma5?: number | null;
  ma10?: number | null;
  ma20?: number | null;
  ma60?: number | null;
  ma120?: number | null;
  ma250?: number | null;
  macd_dif?: number | null;
  macd_dea?: number | null;
  macd_histogram?: number | null;
  rsi_6?: number | null;
  rsi_12?: number | null;
  rsi_24?: number | null;
  kdj_k?: number | null;
  kdj_d?: number | null;
  kdj_j?: number | null;
  boll_upper?: number | null;
  boll_middle?: number | null;
  boll_lower?: number | null;
  volume_ratio?: number | null;
}

export interface KLineResponse {
  stock_code: string;
  period: string;
  count: number;
  data: KLineDataPoint[];
}

export const chartApi = {
  combined: (stockCode: string, period: string = 'daily', limit: number = 500) =>
    apiClient.get<KLineResponse>(`/api/chart/combined/${stockCode}`, {
      params: { period, limit },
    }),
  kline: (stockCode: string, period: string = 'daily', limit: number = 500) =>
    apiClient.get<KLineResponse>(`/api/chart/kline/${stockCode}`, {
      params: { period, limit },
    }),
  indicators: (stockCode: string, limit: number = 500) =>
    apiClient.get<KLineResponse>(`/api/chart/indicators/${stockCode}`, {
      params: { limit },
    }),
};
