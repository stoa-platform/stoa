// SPDX-License-Identifier: Apache-2.0
// Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
/**
 * Contracts and Protocol Bindings API Service
 *
 * API client for managing Universal API Contracts (UAC) and their protocol bindings.
 * Used by the Protocol Switcher component.
 */

import { apiClient } from './api';
import {
  Contract,
  ContractCreate,
  ContractListResponse,
  BindingsListResponse,
  EnableBindingResponse,
  DisableBindingResponse,
  ProtocolType,
  PublishContractResponse,
} from '../types';

export const contractsService = {
  /**
   * List all contracts for the current tenant
   */
  async listContracts(params?: {
    page?: number;
    page_size?: number;
    status?: string;
  }): Promise<ContractListResponse> {
    const response = await apiClient.get<ContractListResponse>('/v1/contracts', { params });
    return response.data;
  },

  /**
   * Get a specific contract by ID
   */
  async getContract(contractId: string): Promise<Contract> {
    const response = await apiClient.get<Contract>(`/v1/contracts/${contractId}`);
    return response.data;
  },

  /**
   * Create a new contract
   * Returns basic contract info
   */
  async createContract(data: ContractCreate): Promise<Contract> {
    const response = await apiClient.post<Contract>('/v1/contracts', data);
    return response.data;
  },

  /**
   * Create and publish a contract with enriched response
   * Returns the contract with all auto-generated bindings for the "wow" effect
   *
   * This is the preferred method when you want to show the user
   * what bindings were auto-generated (REST, MCP, GraphQL, etc.)
   */
  async publishContract(data: ContractCreate): Promise<PublishContractResponse> {
    const response = await apiClient.post<PublishContractResponse>(
      '/v1/contracts',
      { ...data, status: 'published' }
    );
    return response.data;
  },

  /**
   * Update a contract
   */
  async updateContract(
    contractId: string,
    data: Partial<ContractCreate>
  ): Promise<Contract> {
    const response = await apiClient.patch<Contract>(`/v1/contracts/${contractId}`, data);
    return response.data;
  },

  /**
   * Delete a contract
   */
  async deleteContract(contractId: string): Promise<void> {
    await apiClient.delete(`/v1/contracts/${contractId}`);
  },

  /**
   * List all protocol bindings for a contract
   * Returns all 5 protocols (REST, MCP, GraphQL, gRPC, Kafka) with their status
   */
  async getBindings(contractId: string): Promise<BindingsListResponse> {
    const response = await apiClient.get<BindingsListResponse>(
      `/v1/contracts/${contractId}/bindings`
    );
    return response.data;
  },

  /**
   * Enable a protocol binding for a contract
   * This triggers the UAC engine to generate the binding (endpoint, tool, etc.)
   */
  async enableBinding(
    contractId: string,
    protocol: ProtocolType
  ): Promise<EnableBindingResponse> {
    const response = await apiClient.post<EnableBindingResponse>(
      `/v1/contracts/${contractId}/bindings`,
      { protocol }
    );
    return response.data;
  },

  /**
   * Disable a protocol binding for a contract
   * The binding is soft-disabled (keeps history)
   */
  async disableBinding(
    contractId: string,
    protocol: ProtocolType
  ): Promise<DisableBindingResponse> {
    const response = await apiClient.delete<DisableBindingResponse>(
      `/v1/contracts/${contractId}/bindings/${protocol}`
    );
    return response.data;
  },
};

export default contractsService;
