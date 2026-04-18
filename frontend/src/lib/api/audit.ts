import { apiClient } from './client';

export interface AuditLogEntry {
  id: string;
  tenant_id: string;
  actor_type: string;
  actor_id?: string | null;
  action: string;
  resource_type?: string | null;
  resource_id?: string | null;
  metadata: Record<string, unknown>;
  created_at?: string | null;
}

interface AuditLogListResponse {
  message: string;
  audit_logs: AuditLogEntry[];
}

export interface ListAuditLogsParams {
  limit?: number;
}

export async function listAuditLogs(
  params: ListAuditLogsParams = {}
): Promise<AuditLogEntry[]> {
  const searchParams: Record<string, string | number> = {};
  if (params.limit) searchParams.limit = params.limit;
  const res = await apiClient
    .get('v1/audit-logs', { searchParams })
    .json<AuditLogListResponse>();
  return res.audit_logs ?? [];
}
