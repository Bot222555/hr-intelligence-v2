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

// ── API Calls ──────────────────────────────────────────────────────

/** GET /fnf/ — list all FnF records */
export async function getFnFList(params?: {
  status?: string;
  page?: number;
  page_size?: number;
}): Promise<FnFListResponse> {
  const { data } = await apiClient.get("/fnf/", { params });
  return data;
}

/** GET /fnf/{id} — single FnF record */
export async function getFnFRecord(id: string): Promise<FnFRecord> {
  const { data } = await apiClient.get(`/fnf/${id}`);
  return data;
}

/** GET /fnf/employee/{employee_id} — FnF for a specific employee */
export async function getEmployeeFnF(employeeId: string): Promise<FnFRecord> {
  const { data } = await apiClient.get(`/fnf/employee/${employeeId}`);
  return data;
}

/** GET /fnf/summary */
export async function getFnFSummary(): Promise<FnFSummary> {
  const { data } = await apiClient.get("/fnf/summary");
  return data;
}
