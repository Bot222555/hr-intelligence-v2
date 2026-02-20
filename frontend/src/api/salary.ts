/**
 * Salary API module — salary slips, CTC breakdown, team salary.
 *
 * All endpoints go through the authenticated apiClient.
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

export interface TeamSalaryItem {
  employee_id: string;
  employee_code: string;
  display_name: string | null;
  designation: string | null;
  department_name: string | null;
  profile_photo_url: string | null;
  gross_earnings: number;
  net_salary: number;
  payment_status: string;
}

export interface TeamSalaryResponse {
  month: number;
  year: number;
  data: TeamSalaryItem[];
  total_gross: number;
  total_net: number;
}

export interface SalarySummary {
  last_month_net: number;
  last_month_gross: number;
  last_month_label: string;
  next_payroll_date: string | null;
  ytd_gross: number;
  ytd_net: number;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function getMySalarySlips(params?: {
  year?: number;
  page?: number;
  page_size?: number;
}): Promise<SalarySlipListResponse> {
  const { data } = await apiClient.get("/salary/my-slips", { params });
  return data;
}

export async function getSalarySlip(slipId: string): Promise<SalarySlip> {
  const { data } = await apiClient.get(`/salary/slips/${slipId}`);
  return data;
}

export async function downloadSalarySlipPdf(slipId: string): Promise<Blob> {
  const { data } = await apiClient.get(`/salary/slips/${slipId}/pdf`, {
    responseType: "blob",
  });
  return data;
}

export async function getCTCBreakdown(): Promise<CTCBreakdown> {
  const { data } = await apiClient.get("/salary/ctc-breakdown");
  return data;
}

export async function getTeamSalary(params: {
  month: number;
  year: number;
}): Promise<TeamSalaryResponse> {
  const { data } = await apiClient.get("/salary/team", { params });
  return data;
}

export async function getSalarySummary(): Promise<SalarySummary> {
  const { data } = await apiClient.get("/salary/summary");
  return data;
}
