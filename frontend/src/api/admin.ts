/**
 * Admin API — leave types, shift policies, holidays, roles.
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

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
}

export interface LeaveTypeCreate {
  code: string;
  name: string;
  description?: string;
  default_balance?: number;
  max_carry_forward?: number;
  is_paid?: boolean;
  requires_approval?: boolean;
  min_days_notice?: number;
  max_consecutive_days?: number | null;
  applicable_gender?: string | null;
}

export interface ShiftPolicy {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
  grace_minutes: number;
  half_day_minutes: number;
  full_day_minutes: number;
  is_night_shift: boolean;
  is_active: boolean;
}

export interface ShiftPolicyCreate {
  name: string;
  start_time: string;
  end_time: string;
  grace_minutes?: number;
  half_day_minutes?: number;
  full_day_minutes?: number;
  is_night_shift?: boolean;
}

export interface Holiday {
  id: string;
  name: string;
  date: string;
  type: "national" | "restricted" | "optional";
  is_active: boolean;
  calendar_id: string;
}

export interface HolidayCreate {
  name: string;
  date: string;
  type?: "national" | "restricted" | "optional";
}

export interface EmployeeRole {
  employee_id: string;
  employee_number: string;
  display_name: string;
  email: string;
  role: string;
  department: string | null;
}

// ── Leave Types ────────────────────────────────────────────────────

export async function getLeaveTypes(): Promise<LeaveType[]> {
  const { data } = await apiClient.get("/admin/leave-types");
  return data;
}

export async function createLeaveType(body: LeaveTypeCreate): Promise<LeaveType> {
  const { data } = await apiClient.post("/admin/leave-types", body);
  return data;
}

export async function updateLeaveType(
  id: string,
  body: Partial<LeaveType>
): Promise<LeaveType> {
  const { data } = await apiClient.put(`/admin/leave-types/${id}`, body);
  return data;
}

// ── Shift Policies ─────────────────────────────────────────────────

export async function getShiftPolicies(): Promise<ShiftPolicy[]> {
  const { data } = await apiClient.get("/admin/shift-policies");
  return data;
}

export async function createShiftPolicy(body: ShiftPolicyCreate): Promise<ShiftPolicy> {
  const { data } = await apiClient.post("/admin/shift-policies", body);
  return data;
}

export async function updateShiftPolicy(
  id: string,
  body: Partial<ShiftPolicy>
): Promise<ShiftPolicy> {
  const { data } = await apiClient.put(`/admin/shift-policies/${id}`, body);
  return data;
}

// ── Holidays ───────────────────────────────────────────────────────

export async function getHolidays(year?: number): Promise<Holiday[]> {
  const params = year ? { year } : {};
  const { data } = await apiClient.get("/admin/holidays", { params });
  return data;
}

export async function createHoliday(body: HolidayCreate): Promise<Holiday> {
  const { data } = await apiClient.post("/admin/holidays", body);
  return data;
}

export async function updateHoliday(
  id: string,
  body: Partial<Holiday>
): Promise<Holiday> {
  const { data } = await apiClient.put(`/admin/holidays/${id}`, body);
  return data;
}

export async function deleteHoliday(id: string): Promise<void> {
  await apiClient.delete(`/admin/holidays/${id}`);
}

export async function seedHolidays2026(): Promise<{ message: string; created: number }> {
  const { data } = await apiClient.post("/admin/holidays/seed-2026");
  return data;
}

// ── Roles ──────────────────────────────────────────────────────────

export async function getRoles(): Promise<EmployeeRole[]> {
  const { data } = await apiClient.get("/admin/roles");
  return data;
}

export async function assignRole(
  employee_id: string,
  role: string
): Promise<EmployeeRole> {
  const { data } = await apiClient.put("/admin/roles", { employee_id, role });
  return data;
}
