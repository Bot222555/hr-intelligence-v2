/**
 * Employees API module — employee directory, departments, locations,
 * and rich employee profile data.
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export interface DepartmentBrief {
  id: string;
  name: string;
  code: string | null;
}

export interface LocationBrief {
  id: string;
  name: string;
  city: string | null;
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  display_name: string | null;
  email: string;
  designation: string | null;
  profile_photo_url: string | null;
}

export interface EmployeeListItem {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  display_name: string | null;
  email: string;
  phone: string | null;
  designation: string | null;
  job_title: string | null;
  employment_status: string;
  date_of_joining: string;
  is_active: boolean;
  department: DepartmentBrief | null;
  location: LocationBrief | null;
  profile_photo_url: string | null;
}

export interface EmployeeDetail {
  id: string;
  employee_code: string;
  first_name: string;
  middle_name: string | null;
  last_name: string;
  display_name: string | null;
  email: string;
  personal_email: string | null;
  phone: string | null;
  gender: string | null;
  date_of_birth: string | null;
  blood_group: string | null;
  marital_status: string | null;
  nationality: string;
  current_address: Record<string, string> | null;
  permanent_address: Record<string, string> | null;
  emergency_contact: Record<string, string> | null;
  department: DepartmentBrief | null;
  location: LocationBrief | null;
  job_title: string | null;
  designation: string | null;
  reporting_manager: EmployeeSummary | null;
  l2_manager: EmployeeSummary | null;
  employment_status: string;
  date_of_joining: string;
  date_of_confirmation: string | null;
  probation_end_date: string | null;
  resignation_date: string | null;
  last_working_date: string | null;
  date_of_exit: string | null;
  exit_reason: string | null;
  notice_period_days: number;
  profile_photo_url: string | null;
  professional_summary: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  direct_reports_count: number;
}

export interface AttendanceSummary {
  present_days: number;
  half_days: number;
  late_count: number;
  avg_check_in: string | null;
  total_working_days: number;
}

export interface AttendanceDayRecord {
  date: string;
  status: string;
  arrival_status: string | null;
  first_clock_in: string | null;
  last_clock_out: string | null;
  total_work_minutes: number | null;
}

export interface LeaveTypeBrief {
  id: string;
  code: string;
  name: string;
  is_paid?: boolean;
}

export interface LeaveBalanceItem {
  leave_type: LeaveTypeBrief | null;
  opening_balance: number;
  accrued: number;
  used: number;
  carry_forwarded: number;
  adjusted: number;
  current_balance: number;
}

export interface RecentLeaveRequest {
  id: string;
  leave_type: { id: string; code: string; name: string } | null;
  start_date: string;
  end_date: string;
  total_days: number;
  status: string;
  reason: string | null;
  created_at: string;
}

export interface TeamMember {
  id: string;
  employee_code: string;
  display_name: string;
  designation: string | null;
  department: string | null;
  profile_photo_url: string | null;
  email: string;
}

export interface EmployeeProfileData {
  employee: EmployeeDetail;
  attendance_summary: AttendanceSummary;
  recent_attendance: AttendanceDayRecord[];
  month_attendance: AttendanceDayRecord[];
  leave_balances: LeaveBalanceItem[];
  recent_leaves: RecentLeaveRequest[];
  team_members: TeamMember[];
}

export interface EmployeeProfileResponse {
  data: EmployeeProfileData;
  message: string;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface EmployeeListResponse {
  data: EmployeeListItem[];
  meta: PaginationMeta;
}

export interface Department {
  id: string;
  name: string;
}

export interface Location {
  id: string;
  name: string;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function getEmployees(params?: {
  search?: string;
  department_id?: string;
  location_id?: string;
  page?: number;
  page_size?: number;
}): Promise<EmployeeListResponse> {
  const { data } = await apiClient.get("/employees", { params });
  return data;
}

export async function getEmployeeProfile(
  employeeId: string,
): Promise<EmployeeProfileResponse> {
  const { data } = await apiClient.get(`/employees/${employeeId}/profile`);
  return data;
}

export async function getDepartments(): Promise<{ data: Department[]; message: string }> {
  const { data } = await apiClient.get("/departments");
  return data;
}

export async function getLocations(): Promise<{ data: Location[]; message: string }> {
  const { data } = await apiClient.get("/locations");
  return data;
}
