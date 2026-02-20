/**
 * Expenses API module — expense claims, approvals, summaries.
 *
 * All endpoints go through the authenticated apiClient.
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export type ExpenseStatus = "draft" | "submitted" | "approved" | "rejected" | "reimbursed";
export type ExpenseCategory =
  | "travel"
  | "food"
  | "accommodation"
  | "office_supplies"
  | "client_entertainment"
  | "training"
  | "miscellaneous";

export interface ExpenseItem {
  id: string;
  description: string;
  category: ExpenseCategory;
  amount: number;
  receipt_url: string | null;
  date: string;
}

export interface EmployeeBrief {
  id: string;
  employee_code: string;
  display_name: string | null;
  designation: string | null;
  department_name: string | null;
  profile_photo_url: string | null;
}

export interface ExpenseClaim {
  id: string;
  claim_number: string;
  employee_id: string;
  employee: EmployeeBrief | null;
  title: string;
  description: string | null;
  category: ExpenseCategory;
  total_amount: number;
  status: ExpenseStatus;
  items: ExpenseItem[];
  receipt_urls: string[];
  reviewed_by: string | null;
  reviewer: EmployeeBrief | null;
  reviewed_at: string | null;
  reviewer_remarks: string | null;
  reimbursed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ExpenseListResponse {
  data: ExpenseClaim[];
  meta: PaginationMeta;
}

export interface ExpenseSummary {
  total_claimed: number;
  total_approved: number;
  total_pending: number;
  total_rejected: number;
  total_reimbursed: number;
  claims_count: number;
  pending_count: number;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function getMyExpenses(params?: {
  status?: ExpenseStatus;
  category?: ExpenseCategory;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  const { data } = await apiClient.get("/expenses/my-claims", { params });
  return data;
}

export async function getExpenseClaim(claimId: string): Promise<ExpenseClaim> {
  const { data } = await apiClient.get(`/expenses/claims/${claimId}`);
  return data;
}

export async function createExpenseClaim(body: {
  title: string;
  description?: string;
  category: ExpenseCategory;
  total_amount: number;
  receipt_urls?: string[];
}): Promise<ExpenseClaim> {
  const { data } = await apiClient.post("/expenses/claims", body);
  return data;
}

export async function uploadReceipt(file: File): Promise<{ url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post("/expenses/upload-receipt", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function getTeamExpenses(params?: {
  status?: ExpenseStatus;
  employee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  const { data } = await apiClient.get("/expenses/team-claims", { params });
  return data;
}

export async function approveExpense(
  claimId: string,
  remarks?: string,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.put(`/expenses/claims/${claimId}/approve`, {
    remarks,
  });
  return data;
}

export async function rejectExpense(
  claimId: string,
  reason: string,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.put(`/expenses/claims/${claimId}/reject`, {
    reason,
  });
  return data;
}

export async function getExpenseSummary(): Promise<ExpenseSummary> {
  const { data } = await apiClient.get("/expenses/summary");
  return data;
}
