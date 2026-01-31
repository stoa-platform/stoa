/**
 * Client Management Hooks (CAB-870)
 *
 * React Query hooks for mTLS client certificate operations.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '../services/api';
import type { Client, ClientCreate, ClientWithCertificate, RotateRequest } from '../types/client';

export function useClients(options?: { enabled?: boolean }) {
  return useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => apiService.getClients(),
    enabled: options?.enabled ?? true,
    staleTime: 5000,
  });
}

export function useClient(clientId: string | null, options?: { enabled?: boolean }) {
  return useQuery<Client>({
    queryKey: ['clients', clientId],
    queryFn: () => apiService.getClient(clientId!),
    enabled: (options?.enabled ?? true) && !!clientId,
    staleTime: 5000,
  });
}

export function useCreateClient() {
  const queryClient = useQueryClient();
  return useMutation<ClientWithCertificate, Error, ClientCreate>({
    mutationFn: (body) => apiService.createClient(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}

export function useRotateClient() {
  const queryClient = useQueryClient();
  return useMutation<ClientWithCertificate, Error, { clientId: string; body: RotateRequest }>({
    mutationFn: ({ clientId, body }) => apiService.rotateClient(clientId, body),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
      queryClient.invalidateQueries({ queryKey: ['clients', variables.clientId] });
    },
  });
}

export function useRevokeClient() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (clientId) => apiService.revokeClient(clientId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] });
    },
  });
}
