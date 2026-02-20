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
  is_taxable: boolean;
}

export interface SalarySlip {
  id: string;
  employee_id: string;
  month: number;
  year: number;
  basic_salary: number;
  gross_earnings: number;
  total_deductions: number;
  net_salary: number;
  employer_contributions: number;
  ctc_monthly: number;
  components: SalaryComponent[];
  generated_at: string;
  payment_date: string | null;
  payment_status: "pending" | "processed" | "paid" | "failed";
  days_worked: number;
  days_payable: number;
  loss_of_pay_days: number;
}

export interface SalarySlipListResponse {
  data: SalarySlip[];
  total: number;
}

export interface CTCBreakdown {
  annual_ctc: number;
  monthly_ctc: number;
  components: {
    name: string;
    type: "earning" | "deduction" | "employer_contribution";
    annual_amount: number;
    monthly_amount: number;
    percentage_of_ctc: number;
  }[];
}

export interface SalarySummary {
  last_month_net: number;
  last_month_gross: number;
  last_month_label: string;
  next_payroll_date: string | null;
  ytd_gross: number;
  ytd_net: number;
}

export interface SalaryComponentDef {
  id: string;
  name: string;
  type: "earning" | "deduction" | "employer_contribution";
  is_taxable: boolean;
  is_active: boolean;
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /salary/my-salary — current user's salary summary */
export async function getSalarySummary(): Promise<SalarySummary> {
  const { data } = await apiClient.get("/salary/my-salary");
  return data;
}

/** GET /salary/slips — list of salary slips for current user */
export async function getMySalarySlips(params?: {
  year?: number;
  page?: number;
  page_size?: number;
}): Promise<SalarySlipListResponse> {
  const { data } = await apiClient.get("/salary/slips", { params });
  return data;
}

/** GET /salary/components — all salary component definitions */
export async function getSalaryComponents(): Promise<SalaryComponentDef[]> {
  const { data } = await apiClient.get("/salary/components");
  return data;
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
