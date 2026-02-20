/**
 * Dashboard API module — summary, attendance trend, department headcount,
 * upcoming birthdays, and recent activities.
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface DashboardSummary {
  total_employees: number;
  present_today: number;
  on_leave_today: number;
  pending_approvals: number;
  new_joiners_this_month: number;
  attrition_this_month: number;
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

// ── API Calls ──────────────────────────────────────────────────────

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await apiClient.get("/dashboard/summary");
  return data;
}

export async function getAttendanceTrend(
  days: number = 7,
): Promise<AttendanceTrendResponse> {
  const { data } = await apiClient.get("/dashboard/attendance-trend", {
    params: { days },
  });
  return data;
}

export async function getDepartmentHeadcount(): Promise<DepartmentHeadcountResponse> {
  const { data } = await apiClient.get("/dashboard/department-headcount");
  return data;
}

export async function getUpcomingBirthdays(
  days: number = 30,
): Promise<UpcomingBirthdaysResponse> {
  const { data } = await apiClient.get("/dashboard/upcoming-birthdays", {
    params: { days },
  });
  return data;
}

export async function getRecentActivities(
  limit: number = 20,
): Promise<RecentActivitiesResponse> {
  const { data } = await apiClient.get("/dashboard/recent-activities", {
    params: { limit },
  });
  return data;
}
