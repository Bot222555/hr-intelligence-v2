/**
 * Expenses API module — expense claims, approvals.
 *
 * All endpoints go through the authenticated apiClient.
 *
 * Backend routes:
 *   GET   /expenses/              — list all expenses
 *   GET   /expenses/my-expenses   — current user's expenses
 *   GET   /expenses/{id}          — single expense detail
 *   POST  /expenses/              — create expense
 *   PATCH /expenses/{id}          — update expense
 *   POST  /expenses/{id}/approve  — approve expense
 *   POST  /expenses/{id}/reject   — reject expense
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

// ── API Calls ──────────────────────────────────────────────────────

/** GET /expenses/my-expenses — current user's expense claims */
export async function getMyExpenses(params?: {
  status?: ExpenseStatus;
  category?: ExpenseCategory;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  const { data } = await apiClient.get("/expenses/my-expenses", { params });
  return data;
}

/** GET /expenses/{id} — single expense claim detail */
export async function getExpenseClaim(claimId: string): Promise<ExpenseClaim> {
  const { data } = await apiClient.get(`/expenses/${claimId}`);
  return data;
}

/** POST /expenses/ — create a new expense claim */
export async function createExpenseClaim(body: {
  title: string;
  description?: string;
  category: ExpenseCategory;
  total_amount: number;
  receipt_urls?: string[];
}): Promise<ExpenseClaim> {
  const { data } = await apiClient.post("/expenses/", body);
  return data;
}

/** PATCH /expenses/{id} — update an expense claim */
export async function updateExpenseClaim(
  claimId: string,
  body: Partial<{
    title: string;
    description: string;
    category: ExpenseCategory;
    total_amount: number;
    receipt_urls: string[];
    status: ExpenseStatus;
  }>,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.patch(`/expenses/${claimId}`, body);
  return data;
}

/** GET /expenses/ — all expenses (admin/manager view) */
export async function getTeamExpenses(params?: {
  status?: ExpenseStatus;
  employee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  const { data } = await apiClient.get("/expenses/", { params });
  return data;
}

/** POST /expenses/{id}/approve */
export async function approveExpense(
  claimId: string,
  remarks?: string,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.post(`/expenses/${claimId}/approve`, {
    remarks,
  });
  return data;
}

/** POST /expenses/{id}/reject */
export async function rejectExpense(
  claimId: string,
  reason: string,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.post(`/expenses/${claimId}/reject`, {
    reason,
  });
  return data;
}
