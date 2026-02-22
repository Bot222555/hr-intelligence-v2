/**
 * Dashboard API module — summary, attendance trend, department headcount,
 * birthdays, new joiners, leave summary, and recent activities.
 *
 * Backend routes:
 *   GET /dashboard/summary
 *   GET /dashboard/attendance-trend
 *   GET /dashboard/leave-summary
 *   GET /dashboard/birthdays
 *   GET /dashboard/new-joiners
 *   GET /dashboard/department-headcount
 *   GET /dashboard/recent-activities
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface DashboardSummary {
  total_employees: number;
  present_today: number;
  on_leave_today: number;
  pending_leave_requests: number;
  [key: string]: number; // allow extra fields from backend
}

export interface AttendanceTrendPoint {
  date: string;
  present: number;
  absent: number;
  on_leave: number;
  work_from_home: number;
  half_day: number;
}

export interface AttendanceTrendAverages {
  avg_present: number;
  avg_absent: number;
  avg_on_leave: number;
  avg_attendance_rate: number;
}

export interface AttendanceTrendResponse {
  period_days: number;
  start_date: string;
  end_date: string;
  data: AttendanceTrendPoint[];
  averages: AttendanceTrendAverages;
}

export interface DepartmentHeadcountItem {
  department_id: string;
  department_name: string;
  headcount: number;
  present_today: number;
  on_leave_today: number;
}

export interface DepartmentHeadcountResponse {
  total_departments: number;
  data: DepartmentHeadcountItem[];
}

export interface UpcomingBirthdayItem {
  employee_id: string;
  employee_code: string;
  display_name: string | null;
  department_name: string | null;
  date_of_birth: string;
  birthday_date: string;
  days_away: number;
  profile_photo_url: string | null;
}

export interface UpcomingBirthdaysResponse {
  days_ahead: number;
  data: UpcomingBirthdayItem[];
}

export interface RecentActivityItem {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  actor_id: string | null;
  actor_name: string | null;
  description: string;
  created_at: string;
}

export interface RecentActivitiesResponse {
  limit: number;
  data: RecentActivityItem[];
}

export interface LeaveSummaryItem {
  leave_type_id: string;
  leave_type_code: string;
  leave_type_name: string;
  request_count: number;
  total_days: number;
}

export interface LeaveSummaryResponse {
  month: number;
  year: number;
  total_requests: number;
  total_days: number;
  by_type: LeaveSummaryItem[];
}

export interface NewJoinerItem {
  employee_id: string;
  employee_code: string;
  display_name: string | null;
  department_name: string | null;
  designation: string | null;
  date_of_joining: string;
  profile_photo_url: string | null;
}

export interface NewJoinersResponse {
  data: NewJoinerItem[];
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /dashboard/summary */
export async function getDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await apiClient.get("/dashboard/summary");
  return data;
}

/** GET /dashboard/attendance-trend */
export async function getAttendanceTrend(
  days: number = 7,
): Promise<AttendanceTrendResponse> {
  const { data } = await apiClient.get("/dashboard/attendance-trend", {
    params: { days },
  });
  return data;
}

/** GET /dashboard/department-headcount */
export async function getDepartmentHeadcount(): Promise<DepartmentHeadcountResponse> {
  const { data } = await apiClient.get("/dashboard/department-headcount");
  return data;
}

/** GET /dashboard/birthdays */
export async function getUpcomingBirthdays(
  days: number = 30,
): Promise<UpcomingBirthdaysResponse> {
  const { data } = await apiClient.get("/dashboard/birthdays", {
    params: { days },
  });
  return data;
}

/** GET /dashboard/recent-activities */
export async function getRecentActivities(
  limit: number = 20,
): Promise<RecentActivitiesResponse> {
  const { data } = await apiClient.get("/dashboard/recent-activities", {
    params: { limit },
  });
  return data;
}

/** GET /dashboard/leave-summary */
export async function getLeaveSummary(): Promise<LeaveSummaryResponse> {
  const { data } = await apiClient.get("/dashboard/leave-summary");
  return data;
}

/** GET /dashboard/new-joiners */
export async function getNewJoiners(): Promise<NewJoinersResponse> {
  const { data } = await apiClient.get("/dashboard/new-joiners");
  return data;
}
