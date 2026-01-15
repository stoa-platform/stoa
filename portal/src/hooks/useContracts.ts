/**
 * STOA Developer Portal - Contract & Bindings Hooks
 *
 * React Query hooks for managing Universal API Contracts (UAC) and their protocol bindings.
 * Used by the Protocol Switcher component.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { contractsService } from '../services/contracts';
import type {
  Contract,
  ContractCreate,
  ContractListResponse,
  BindingsListResponse,
  EnableBindingResponse,
  DisableBindingResponse,
  ProtocolType,
} from '../types';

// ============ Contract Hooks ============

/**
 * Hook to list contracts for the current tenant
 */
export function useContracts(params?: {
  page?: number;
  page_size?: number;
  status?: string;
}) {
  return useQuery<ContractListResponse>({
    queryKey: ['contracts', params],
    queryFn: () => contractsService.listContracts(params),
    staleTime: 30 * 1000, // 30 seconds
  });
}

/**
 * Hook to get a single contract by ID
 */
export function useContract(contractId: string | undefined) {
  return useQuery<Contract>({
    queryKey: ['contract', contractId],
    queryFn: () => contractsService.getContract(contractId!),
    enabled: !!contractId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to create a new contract
 */
export function useCreateContract() {
  const queryClient = useQueryClient();

  return useMutation<Contract, Error, ContractCreate>({
    mutationFn: (data) => contractsService.createContract(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
}

/**
 * Hook to update a contract
 */
export function useUpdateContract(contractId: string) {
  const queryClient = useQueryClient();

  return useMutation<Contract, Error, Partial<ContractCreate>>({
    mutationFn: (data) => contractsService.updateContract(contractId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
}

/**
 * Hook to delete a contract
 */
export function useDeleteContract() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: (contractId) => contractsService.deleteContract(contractId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
    },
  });
}

// ============ Bindings Hooks ============

/**
 * Hook to get all protocol bindings for a contract
 * Returns all 5 protocols with their enabled/disabled status
 */
export function useBindings(contractId: string | undefined) {
  return useQuery<BindingsListResponse>({
    queryKey: ['bindings', contractId],
    queryFn: () => contractsService.getBindings(contractId!),
    enabled: !!contractId,
    staleTime: 30 * 1000,
  });
}

/**
 * Hook to enable a protocol binding
 * Triggers UAC engine to generate the binding (endpoint, tool, etc.)
 */
export function useEnableBinding(contractId: string) {
  const queryClient = useQueryClient();

  return useMutation<EnableBindingResponse, Error, ProtocolType>({
    mutationFn: (protocol) => contractsService.enableBinding(contractId, protocol),
    onSuccess: () => {
      // Invalidate bindings cache to refresh the list
      queryClient.invalidateQueries({ queryKey: ['bindings', contractId] });
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
}

/**
 * Hook to disable a protocol binding
 */
export function useDisableBinding(contractId: string) {
  const queryClient = useQueryClient();

  return useMutation<DisableBindingResponse, Error, ProtocolType>({
    mutationFn: (protocol) => contractsService.disableBinding(contractId, protocol),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bindings', contractId] });
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
    },
  });
}
