/**
 * Attendance API module — clock in/out, attendance records, regularization, holidays.
 *
 * All endpoints go through the authenticated apiClient.
 */

import apiClient from "./client";

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

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
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

// ── Clock In / Out ─────────────────────────────────────────────────

export async function clockIn(
  source: string = "web",
): Promise<ClockResponse> {
  const { data } = await apiClient.post("/attendance/clock-in", { source });
  return data;
}

export async function clockOut(
  source: string = "web",
): Promise<ClockResponse> {
  const { data } = await apiClient.post("/attendance/clock-out", { source });
  return data;
}

// ── My Attendance ──────────────────────────────────────────────────

export async function getMyAttendance(
  fromDate: string,
  toDate: string,
  page: number = 1,
  pageSize: number = 50,
): Promise<AttendanceListResponse> {
  const { data } = await apiClient.get("/attendance/my-attendance", {
    params: { from_date: fromDate, to_date: toDate, page, page_size: pageSize },
  });
  return data;
}

// ── Today (Manager/HR view) ────────────────────────────────────────

export async function getTodayAttendance(params?: {
  department_id?: string;
  location_id?: string;
  status?: AttendanceStatus;
}): Promise<TodayAttendanceResponse> {
  const { data } = await apiClient.get("/attendance/today", { params });
  return data;
}

// ── Team Attendance ────────────────────────────────────────────────

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

export async function getRegularizations(params?: {
  status?: RegularizationStatus;
  employee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<RegularizationListResponse> {
  const { data } = await apiClient.get("/attendance/regularizations", { params });
  return data;
}

// ── Holidays ───────────────────────────────────────────────────────

export async function getHolidays(params?: {
  year?: number;
  location_id?: string;
}): Promise<Holiday[]> {
  const { data } = await apiClient.get("/attendance/holidays", { params });
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
