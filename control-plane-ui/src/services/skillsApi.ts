/**
 * Skills API Service (CAB-1366)
 *
 * Client for managing agent skills via the gateway admin API.
 * Skills use a CSS cascade model: global(0) < tenant(1) < tool(2) < user(3).
 */

import { apiService } from './api';

export interface SkillEntry {
  key: string;
  name: string;
  description: string | null;
  tenant_id: string;
  scope: string;
  priority: number;
  instructions: string | null;
  tool_ref: string | null;
  user_ref: string | null;
  enabled: boolean;
}

export interface SkillUpsert {
  key: string;
  name: string;
  description?: string;
  tenant_id: string;
  scope: string;
  priority?: number;
  instructions?: string;
  tool_ref?: string;
  user_ref?: string;
  enabled?: boolean;
}

export interface ResolvedSkill {
  name: string;
  scope: string;
  priority: number;
  instructions: string | null;
  specificity: number;
}

class SkillsService {
  /**
   * List all stored skills.
   * Endpoint: GET /v1/gateway/admin/skills
   */
  async listSkills(): Promise<SkillEntry[]> {
    const { data } = await apiService.get<SkillEntry[]>('/v1/gateway/admin/skills');
    return data;
  }

  /**
   * Create or update a skill.
   * Endpoint: POST /v1/gateway/admin/skills
   */
  async upsertSkill(payload: SkillUpsert): Promise<{ key: string }> {
    const { data } = await apiService.post<{ key: string }>('/v1/gateway/admin/skills', payload);
    return data;
  }

  /**
   * Delete a skill by key.
   * Endpoint: DELETE /v1/gateway/admin/skills?key=X
   */
  async deleteSkill(key: string): Promise<void> {
    await apiService.delete(`/v1/gateway/admin/skills?key=${encodeURIComponent(key)}`);
  }

  /**
   * Resolve skills for a context (CSS cascade).
   * Endpoint: GET /v1/gateway/admin/skills/resolve?tenant_id=X&tool_ref=Y&user_ref=Z
   */
  async resolveSkills(
    tenantId: string,
    toolRef?: string,
    userRef?: string
  ): Promise<ResolvedSkill[]> {
    const params = new URLSearchParams({ tenant_id: tenantId });
    if (toolRef) params.set('tool_ref', toolRef);
    if (userRef) params.set('user_ref', userRef);
    const { data } = await apiService.get<ResolvedSkill[]>(
      `/v1/gateway/admin/skills/resolve?${params.toString()}`
    );
    return data;
  }
}

export const skillsService = new SkillsService();
