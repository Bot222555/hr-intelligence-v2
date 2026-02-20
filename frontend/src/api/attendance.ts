/**
 * Attendance API module — clock in/out, attendance records, regularization,
 * holidays, shifts, policies.
 *
 * All endpoints go through the authenticated apiClient.
 *
 * Backend routes:
 *   GET  /attendance/today
 *   GET  /attendance/my-attendance
 *   GET  /attendance/team
 *   POST /attendance/clock-in
 *   POST /attendance/clock-out
 *   POST /attendance/regularization
 *   PUT  /attendance/regularizations/{id}/approve
 *   GET  /attendance/shifts
 *   GET  /attendance/holidays
 *   GET  /attendance/policies
 */

import apiClient from "./client";
import type { PaginationMeta } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────

export type AttendanceStatus =
  | "present"
  | "absent"
  | "half_day"
  | "weekend"
  | "holiday"
  | "on_leave"
  | "work_from_home"
  | "on_duty";

export type ArrivalStatus = "on_time" | "late" | "very_late" | "absent";

export type RegularizationStatus = "pending" | "approved" | "rejected";

export interface ShiftBrief {
  id: string;
  name: string;
  start_time: string;
  end_time: string;
}

export interface AttendanceRecord {
  id: string;
  date: string;
  first_clock_in: string | null;
  last_clock_out: string | null;
  total_hours: number | null;
  effective_hours: number | null;
  overtime_hours: number;
  status: AttendanceStatus;
  arrival_status: ArrivalStatus | null;
  shift: ShiftBrief | null;
  is_regularized: boolean;
  source: string;
  remarks: string | null;
}

export interface AttendanceSummary {
  present: number;
  absent: number;
  half_day: number;
  late: number;
  very_late: number;
  avg_hours: number;
  total_overtime: number;
}

export interface AttendanceListResponse {
  data: AttendanceRecord[];
  meta: PaginationMeta;
  summary: AttendanceSummary;
}

export interface ClockResponse {
  clock_entry_id: string;
  attendance_id: string;
  timestamp: string;
  status: AttendanceStatus;
  arrival_status: ArrivalStatus | null;
}

export interface EmployeeBrief {
  id: string;
  employee_code: string;
  display_name: string | null;
  designation: string | null;
  department_name: string | null;
  profile_photo_url: string | null;
}

export interface TodayAttendanceItem {
  employee: EmployeeBrief;
  status: AttendanceStatus;
  arrival_status: ArrivalStatus | null;
  first_clock_in: string | null;
  last_clock_out: string | null;
  total_hours: number | null;
  shift_name: string | null;
}

export interface TodaySummary {
  total_employees: number;
  present: number;
  absent: number;
  on_leave: number;
  work_from_home: number;
  not_clocked_in_yet: number;
}

export interface TodayAttendanceResponse {
  data: TodayAttendanceItem[];
  summary: TodaySummary;
}

export interface RegularizationRecord {
  id: string;
  attendance_record_id: string;
  employee_id: string;
  requested_status: AttendanceStatus;
  reason: string;
  status: RegularizationStatus;
  reviewed_by: string | null;
  reviewed_at: string | null;
  reviewer_remarks: string | null;
  created_at: string;
  updated_at: string;
}

export interface RegularizationListResponse {
  data: RegularizationRecord[];
  meta: PaginationMeta;
}

export interface Holiday {
  id: string;
  name: string;
  date: string;
  is_optional: boolean;
  is_restricted: boolean;
  calendar_id: string;
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

export interface AttendancePolicy {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

// ── Clock In / Out ─────────────────────────────────────────────────

/** POST /attendance/clock-in */
export async function clockIn(
  source: string = "web",
): Promise<ClockResponse> {
  const { data } = await apiClient.post("/attendance/clock-in", { source });
  return data;
}

/** POST /attendance/clock-out */
export async function clockOut(
  source: string = "web",
): Promise<ClockResponse> {
  const { data } = await apiClient.post("/attendance/clock-out", { source });
  return data;
}

// ── My Attendance ──────────────────────────────────────────────────

/** GET /attendance/my-attendance — defaults to last 30 days if dates omitted */
export async function getMyAttendance(
  fromDate?: string,
  toDate?: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<AttendanceListResponse> {
  const now = new Date();
  const resolvedTo = toDate || now.toISOString().split("T")[0];
  const resolvedFrom =
    fromDate ||
    new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      .toISOString()
      .split("T")[0];
  const { data } = await apiClient.get("/attendance/my-attendance", {
    params: {
      from_date: resolvedFrom,
      to_date: resolvedTo,
      page,
      page_size: pageSize,
    },
  });
  return data;
}

// ── Today (Manager/HR view) ────────────────────────────────────────

/** GET /attendance/today */
export async function getTodayAttendance(params?: {
  department_id?: string;
  location_id?: string;
  status?: AttendanceStatus;
}): Promise<TodayAttendanceResponse> {
  const { data } = await apiClient.get("/attendance/today", { params });
  return data;
}

// ── Team Attendance ────────────────────────────────────────────────

/** GET /attendance/team */
export async function getTeamAttendance(
  fromDate: string,
  toDate: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<AttendanceListResponse> {
  const { data } = await apiClient.get("/attendance/team", {
    params: { from_date: fromDate, to_date: toDate, page, page_size: pageSize },
  });
  return data;
}

// ── Regularization ─────────────────────────────────────────────────

/** GET /attendance/regularizations — list regularization requests (inferred from PUT /attendance/regularizations/{id}/approve) */
export async function getRegularizations(params?: {
  status?: RegularizationStatus;
  page?: number;
  page_size?: number;
}): Promise<RegularizationListResponse> {
  try {
    const { data } = await apiClient.get("/attendance/regularizations", { params });
    return data;
  } catch {
    // Endpoint may not exist — return empty list gracefully
    return { data: [], meta: { page: 1, page_size: 50, total: 0, total_pages: 0, has_next: false, has_prev: false } };
  }
}

/** POST /attendance/regularization */
export async function submitRegularization(body: {
  date: string;
  requested_status: AttendanceStatus;
  requested_clock_in?: string;
  requested_clock_out?: string;
  reason: string;
}): Promise<RegularizationRecord> {
  const { data } = await apiClient.post("/attendance/regularization", body);
  return data;
}

/** PUT /attendance/regularizations/{id}/approve */
export async function approveRegularization(
  regularizationId: string,
  body?: { remarks?: string },
): Promise<RegularizationRecord> {
  const { data } = await apiClient.put(
    `/attendance/regularizations/${regularizationId}/approve`,
    body ?? {},
  );
  return data;
}

// ── Shifts ─────────────────────────────────────────────────────────

/** GET /attendance/shifts */
export async function getShifts(): Promise<ShiftPolicy[]> {
  const { data } = await apiClient.get("/attendance/shifts");
  return data;
}

// ── Holidays ───────────────────────────────────────────────────────

/** GET /attendance/holidays */
export async function getHolidays(params?: {
  year?: number;
  location_id?: string;
}): Promise<Holiday[]> {
  const { data } = await apiClient.get("/attendance/holidays", { params });
  return data;
}

// ── Policies ───────────────────────────────────────────────────────

/** GET /attendance/policies */
export async function getAttendancePolicies(): Promise<AttendancePolicy[]> {
  const { data } = await apiClient.get("/attendance/policies");
  return data;
}

// ── Departments (for filters) ──────────────────────────────────────

export interface Department {
  id: string;
  name: string;
}

export async function getDepartments(): Promise<{ data: Department[] }> {
  const { data } = await apiClient.get("/departments");
  return data;
}

export interface Location {
  id: string;
  name: string;
}

export async function getLocations(): Promise<{ data: Location[] }> {
  const { data } = await apiClient.get("/locations");
  return data;
}
