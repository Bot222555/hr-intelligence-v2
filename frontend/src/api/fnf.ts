/**
 * Full & Final Settlement API module.
 *
 * Backend routes:
 *   GET /fnf/                    — list all FnF records
 *   GET /fnf/{id}                — single FnF record
 *   GET /fnf/employee/{employee_id} — FnF by employee
 *   GET /fnf/summary             — FnF summary/stats
 */

import apiClient from "./client";
import type { PaginationMeta } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────

export interface FnFRecord {
  id: string;
  employee_id: string;
  employee_name: string | null;
  employee_code: string | null;
  last_working_date: string;
  resignation_date: string | null;
  status: string;
  total_payable: number;
  total_recoverable: number;
  net_settlement: number;
  components: FnFComponent[];
  created_at: string;
  updated_at: string;
}

export interface FnFComponent {
  name: string;
  type: "payable" | "recoverable";
  amount: number;
  remarks: string | null;
}

export interface FnFListResponse {
  data: FnFRecord[];
  meta?: PaginationMeta;
}

export interface FnFSummary {
  total_pending: number;
  total_completed: number;
  total_amount_pending: number;
  total_amount_settled: number;
}

// ── Normalizers ────────────────────────────────────────────────────

/** R2-03: Normalize backend FnFOut → frontend FnFRecord shape */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeFnF(data: any): FnFRecord {
  return {
    id: data.id,
    employee_id: data.employee_id,
    employee_name: data.employee_name ?? data.employee_number ?? null,
    employee_code: data.employee_code ?? data.employee_number ?? null,
    last_working_date: data.last_working_date ?? data.last_working_day ?? "",
    resignation_date: data.resignation_date ?? null,
    status: data.status ?? data.settlement_status ?? "pending",
    total_payable: data.total_payable ?? data.total_earnings ?? 0,
    total_recoverable: data.total_recoverable ?? data.total_deductions ?? 0,
    net_settlement: data.net_settlement ?? 0,
    components: data.components ?? [],
    created_at: data.created_at ?? "",
    updated_at: data.updated_at ?? "",
  };
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /fnf/ — list all FnF records */
export async function getFnFList(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<FnFListResponse> {
  const { data } = await apiClient.get("/fnf/", { params });
  return {
    ...data,
    data: (data.data ?? []).map(normalizeFnF),
  };
}

/** GET /fnf/{id} — single FnF record */
export async function getFnFRecord(id: string): Promise<FnFRecord> {
  const { data } = await apiClient.get(`/fnf/${id}`);
  return normalizeFnF(data);
}

/** GET /fnf/employee/{employee_id} — FnF for a specific employee */
export async function getEmployeeFnF(employeeId: string): Promise<FnFRecord> {
  const { data } = await apiClient.get(`/fnf/employee/${employeeId}`);
  return normalizeFnF(data);
}

/** GET /fnf/summary — R2-04: Normalize summary field names */
export async function getFnFSummary(): Promise<FnFSummary> {
  const { data } = await apiClient.get("/fnf/summary");
  return {
    total_pending: data.total_pending ?? data.pending ?? 0,
    total_completed: data.total_completed ?? data.completed ?? 0,
    total_amount_pending: data.total_amount_pending ?? 0,
    total_amount_settled: data.total_amount_settled ?? data.total_net_amount ?? 0,
  };
}
