import { apiService } from './api';

// --- Types ---

export interface RootCause {
  category: string;
  confidence: number;
  summary: string;
  evidence: string[];
  suggested_fix: string | null;
}

export interface TimingBreakdown {
  gateway_ms: number | null;
  backend_ms: number | null;
  total_ms: number | null;
}

export interface HopInfo {
  protocol: string;
  pseudonym: string;
  latency_ms: number | null;
}

export interface NetworkPath {
  hops: HopInfo[];
  total_hops: number;
  detected_intermediaries: string[];
  total_latency_ms: number;
}

export interface DiagnosticReport {
  id: string;
  timestamp: string;
  tenant_id: string;
  gateway_id: string;
  root_causes: RootCause[];
  timing: TimingBreakdown | null;
  network_path: NetworkPath | null;
  redacted: boolean;
}

export interface ConnectivityStage {
  name: string;
  status: string;
  latency_ms: number | null;
  detail: string | null;
}

export interface ConnectivityResult {
  overall_status: string;
  stages: ConnectivityStage[];
  network_path: NetworkPath | null;
  checked_at: string;
}

// --- API Functions ---

export async function runDiagnostic(gatewayId: string): Promise<DiagnosticReport> {
  const { data } = await apiService.get<DiagnosticReport>(`/v1/admin/diagnostics/${gatewayId}`);
  return data;
}

export async function checkConnectivity(gatewayId: string): Promise<ConnectivityResult> {
  const { data } = await apiService.get<ConnectivityResult>(
    `/v1/admin/diagnostics/${gatewayId}/connectivity`
  );
  return data;
}

export async function getDiagnosticHistory(
  gatewayId: string,
  limit = 20
): Promise<DiagnosticReport[]> {
  const { data } = await apiService.get<DiagnosticReport[]>(
    `/v1/admin/diagnostics/${gatewayId}/history`,
    { params: { limit } }
  );
  return data;
}
