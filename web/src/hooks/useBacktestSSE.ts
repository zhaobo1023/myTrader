'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

interface BacktestStatus {
  job_id: number;
  status: string;
  progress: number;
  stage?: string;
  total_return?: number;
  annual_return?: number;
  max_drawdown?: number;
  sharpe_ratio?: number;
  ic?: number;
  icir?: number;
  error_msg?: string;
  created_at?: string;
  finished_at?: string;
}

export function useBacktestSSE(jobId: number | null) {
  const [status, setStatus] = useState<BacktestStatus | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  const connect = useCallback(() => {
    if (!jobId) return;

    const token = localStorage.getItem('access_token');
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || '';
    const url = `${baseUrl}/api/strategy/backtest/${jobId}/sse?token=${token}`;

    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;
    setIsStreaming(true);

    eventSource.onmessage = (event) => {
      try {
        const data: BacktestStatus = JSON.parse(event.data);
        setStatus(data);

        if (data.status === 'done' || data.status === 'failed') {
          eventSource.close();
          eventSourceRef.current = null;
          setIsStreaming(false);
        }
      } catch {
        // skip
      }
    };

    eventSource.onerror = () => {
      eventSource.close();
      eventSourceRef.current = null;
      setIsStreaming(false);
    };
  }, [jobId]);

  useEffect(() => {
    connect();
    return () => {
      eventSourceRef.current?.close();
    };
  }, [connect]);

  return { status, isStreaming, reconnect: connect };
}
