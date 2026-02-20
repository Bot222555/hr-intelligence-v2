/**
 * Leave API module — balances, requests, team leaves, calendar, policies.
 *
 * All endpoints go through the authenticated apiClient.
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export type LeaveStatus = "pending" | "approved" | "rejected" | "cancelled" | "revoked";
export type LeaveDayType = "full_day" | "first_half" | "second_half";

export interface LeaveTypeBrief {
  id: string;
  code: string;
  name: string;
  is_paid: boolean;
}

export interface LeaveType {
  id: string;
  code: string;
  name: string;
  description: string | null;
  default_balance: number;
  max_carry_forward: number;
  is_paid: boolean;
  requires_approval: boolean;
  min_days_notice: number;
  max_consecutive_days: number | null;
  is_active: boolean;
  applicable_gender: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveBalance {
  id: string;
  employee_id: string;
  leave_type_id: string;
  year: number;
  opening_balance: number;
  accrued: number;
  used: number;
  carry_forwarded: number;
  adjusted: number;
  current_balance: number;
  pending: number;
  available: number;
  leave_type: LeaveTypeBrief | null;
}

export interface EmployeeBrief {
  id: string;
  employee_code: string;
  display_name: string | null;
  designation: string | null;
  department_name: string | null;
  profile_photo_url: string | null;
}

export interface LeaveRequest {
  id: string;
  employee_id: string;
  leave_type_id: string;
  start_date: string;
  end_date: string;
  day_details: Record<string, LeaveDayType>;
  total_days: number;
  reason: string | null;
  status: LeaveStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  reviewer_remarks: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  employee: EmployeeBrief | null;
  leave_type: LeaveTypeBrief | null;
  reviewer: EmployeeBrief | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface LeaveRequestListResponse {
  data: LeaveRequest[];
  meta: PaginationMeta;
}

export interface LeaveCalendarEntry {
  employee: EmployeeBrief;
  leave_type: LeaveTypeBrief;
  start_date: string;
  end_date: string;
  total_days: number;
  status: LeaveStatus;
  day_details: Record<string, LeaveDayType>;
}

export interface LeaveCalendarResponse {
  month: number;
  year: number;
  entries: LeaveCalendarEntry[];
  total_entries: number;
}

// ── Balances ───────────────────────────────────────────────────────

export async function getBalances(year?: number): Promise<LeaveBalance[]> {
  const { data } = await apiClient.get("/leave/balances", {
    params: year ? { year } : undefined,
  });
  return data;
}

// ── Policies (Leave Types) ─────────────────────────────────────────

export async function getPolicies(isActive?: boolean): Promise<LeaveType[]> {
  const { data } = await apiClient.get("/leave/policies", {
    params: isActive !== undefined ? { is_active: isActive } : undefined,
  });
  return data;
}

// ── Apply Leave ────────────────────────────────────────────────────

export interface ApplyLeavePayload {
  leave_type_id: string;
  from_date: string;
  to_date: string;
  reason?: string;
  day_details?: Record<string, LeaveDayType>;
}

export async function applyLeave(body: ApplyLeavePayload): Promise<LeaveRequest> {
  const { data } = await apiClient.post("/leave/apply", body);
  return data;
}

// ── My Leaves ──────────────────────────────────────────────────────

export async function getMyLeaves(params?: {
  status?: LeaveStatus;
  leave_type_id?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<LeaveRequestListResponse> {
  const { data } = await apiClient.get("/leave/my-leaves", { params });
  return data;
}

// ── Team Leaves (Manager) ──────────────────────────────────────────

export async function getTeamLeaves(params?: {
  status?: LeaveStatus;
  employee_id?: string;
  leave_type_id?: string;
  from_date?: string;
  to_date?: string;
  page?: number;
  page_size?: number;
}): Promise<LeaveRequestListResponse> {
  const { data } = await apiClient.get("/leave/team-leaves", { params });
  return data;
}

// ── Approve / Reject ───────────────────────────────────────────────

export async function approveLeave(
  requestId: string,
  remarks?: string,
): Promise<LeaveRequest> {
  const { data } = await apiClient.put(`/leave/${requestId}/approve`, { remarks });
  return data;
}

export async function rejectLeave(
  requestId: string,
  reason: string,
): Promise<LeaveRequest> {
  const { data } = await apiClient.put(`/leave/${requestId}/reject`, { reason });
  return data;
}

// ── Calendar ───────────────────────────────────────────────────────

export async function getLeaveCalendar(params: {
  month: number;
  year: number;
  department_id?: string;
  location_id?: string;
}): Promise<LeaveCalendarResponse> {
  const { data } = await apiClient.get("/leave/calendar", { params });
  return data;
}
