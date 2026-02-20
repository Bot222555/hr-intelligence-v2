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
import type { PaginationMeta } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────

/** Maps to backend ExpenseOut.approval_status */
export type ExpenseStatus = "pending" | "submitted" | "approved" | "rejected" | "reimbursed" | "draft";

export interface ExpenseClaim {
  id: string;
  employee_id: string;
  employee_name: string | null;
  claim_number: string | null;
  title: string;
  amount: number;
  currency: string;
  payment_status: string | null;
  approval_status: string;
  expenses: any[];
  submitted_date: string | null;
  approved_by_id: string | null;
  approved_at: string | null;
  paid_at: string | null;
  remarks: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface ExpenseListResponse {
  data: ExpenseClaim[];
  meta: PaginationMeta;
}

// ── Helpers ────────────────────────────────────────────────────────

/** Normalize flat pagination to nested meta if backend returns flat format */
function normalizeExpenseList(raw: any): ExpenseListResponse {
  if (raw.meta) return raw;
  const total = raw.total ?? 0;
  const page = raw.page ?? 1;
  const page_size = raw.page_size ?? 50;
  const total_pages = Math.max(1, Math.ceil(total / page_size));
  return {
    data: raw.data ?? [],
    meta: {
      page,
      page_size,
      total,
      total_pages,
      has_next: page < total_pages,
      has_prev: page > 1,
    },
  };
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /expenses/my-expenses — current user's expense claims */
export async function getMyExpenses(params?: {
  status?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  // Backend uses approval_status, not status
  const { status, ...rest } = params ?? {};
  const queryParams = status ? { ...rest, approval_status: status } : rest;
  const { data } = await apiClient.get("/expenses/my-expenses", { params: queryParams });
  return normalizeExpenseList(data);
}

/** GET /expenses/{id} — single expense claim detail */
export async function getExpenseClaim(claimId: string): Promise<ExpenseClaim> {
  const { data } = await apiClient.get(`/expenses/${claimId}`);
  return data;
}

/** POST /expenses/ — create a new expense claim */
export async function createExpenseClaim(body: {
  title: string;
  amount: number;
  currency?: string;
  remarks?: string;
}): Promise<ExpenseClaim> {
  const { data } = await apiClient.post("/expenses/", body);
  return data;
}

/** PATCH /expenses/{id} — update an expense claim */
export async function updateExpenseClaim(
  claimId: string,
  body: Partial<{
    title: string;
    amount: number;
    currency: string;
    remarks: string;
  }>,
): Promise<ExpenseClaim> {
  const { data } = await apiClient.patch(`/expenses/${claimId}`, body);
  return data;
}

/** GET /expenses/ — all expenses (admin/manager view) */
export async function getTeamExpenses(params?: {
  status?: string;
  employee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<ExpenseListResponse> {
  const { status, ...rest } = params ?? {};
  const queryParams = status ? { ...rest, approval_status: status } : rest;
  const { data } = await apiClient.get("/expenses/", { params: queryParams });
  return normalizeExpenseList(data);
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
    remarks: reason,
  });
  return data;
}
