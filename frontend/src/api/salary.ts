/**
 * Salary API module — salary slips, CTC breakdown, components, team salary.
 *
 * All endpoints go through the authenticated apiClient.
 *
 * Backend routes:
 *   GET /salary/my-salary
 *   GET /salary/slips
 *   GET /salary/components
 *   GET /salary/my-ctc
 *   GET /salary/{employee_id}/ctc
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface SalaryComponent {
  name: string;
  type: "earning" | "deduction" | "employer_contribution";
  amount: number;
  percentage?: number;
  is_taxable?: boolean;
  annual_amount?: number;
  monthly_amount?: number;
  percentage_of_ctc?: number;
}

/** Maps to backend SalaryOut — CTC-based salary record */
export interface SalarySlip {
  id: string;
  employee_id: string;
  ctc: number;
  gross_pay: number;
  net_pay: number;
  earnings: any[];
  deductions: any[];
  contributions: any[];
  variables: any[];
  effective_date: string | null;
  pay_period: string | null;
  is_current: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SalarySlipListResponse {
  data: SalarySlip[];
  total: number;
}

/** Maps to backend CTCBreakdownOut (enriched with components) */
export interface CTCBreakdown {
  employee_id: string;
  employee_name: string | null;
  annual_ctc: number;
  monthly_ctc: number;
  ctc: number;
  gross_pay: number;
  net_pay: number;
  components: {
    name: string;
    type: "earning" | "deduction" | "employer_contribution";
    annual_amount: number;
    monthly_amount: number;
    percentage_of_ctc: number;
  }[];
  earnings: any[];
  deductions: any[];
  contributions: any[];
}

export interface SalarySummary {
  total_earnings: number;
  total_deductions: number;
  net_pay: number;
}

export interface SalaryComponentDef {
  id: string;
  identifier: string | null;
  title: string;
  accounting_code: string | null;
  component_type: string;
  is_active: boolean;
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /salary/my-salary — current user's salary record */
export async function getSalarySummary(): Promise<SalarySummary> {
  const { data } = await apiClient.get("/salary/my-salary");
  // Normalize SalaryOut to SalarySummary
  return {
    total_earnings: data.gross_pay ?? 0,
    total_deductions: (data.gross_pay ?? 0) - (data.net_pay ?? 0),
    net_pay: data.net_pay ?? 0,
  };
}

/** GET /salary/slips — list of salary records */
export async function getMySalarySlips(params?: {
  year?: number;
  page?: number;
  page_size?: number;
}): Promise<SalarySlipListResponse> {
  const { data } = await apiClient.get("/salary/my-slips", { params });
  return data;
}

/** GET /salary/components — all salary component definitions */
export async function getSalaryComponents(): Promise<SalaryComponentDef[]> {
  const { data } = await apiClient.get("/salary/components");
  return data.data ?? data;
}

/** GET /salary/my-ctc — current user's CTC breakdown */
export async function getCTCBreakdown(): Promise<CTCBreakdown> {
  const { data } = await apiClient.get("/salary/my-ctc");
  return data;
}

/** GET /salary/{employee_id}/ctc — specific employee's CTC (manager/admin) */
export async function getEmployeeCTC(employeeId: string): Promise<CTCBreakdown> {
  const { data } = await apiClient.get(`/salary/${employeeId}/ctc`);
  return data;
}
