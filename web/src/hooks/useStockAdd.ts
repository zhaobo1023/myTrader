import { useMutation, useQueryClient } from '@tanstack/react-query';
import { positionsApi, themePoolApi } from '@/lib/api-client';
import { candidatePoolApi, CandidateAddPayload } from '@/lib/candidate-pool-api';

export function useAddToPositions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Parameters<typeof positionsApi.create>[0]) => positionsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['positions'] });
    },
  });
}

export function useAddToCandidate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CandidateAddPayload) => candidatePoolApi.add(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['candidate-pool'] });
    },
  });
}

export function useAddToTheme() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { themeId: number; stock_code: string; stock_name: string; reason?: string }) =>
      themePoolApi.addStock(data.themeId, data.stock_code, data.stock_name, data.reason),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['theme-pool-stocks', variables.themeId] });
      qc.invalidateQueries({ queryKey: ['theme-pools'] });
    },
  });
}

