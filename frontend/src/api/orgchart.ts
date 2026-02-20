/**
 * Org Chart & Department API module
 */

import apiClient from "./client";
import type { EmployeeListItem, PaginationMeta } from "./employees";

// ── Org Chart Types ────────────────────────────────────────────────

export interface OrgChartNode {
  id: string;
  employee_code: string;
  display_name: string;
  designation: string | null;
  department: string | null;
  profile_photo_url: string | null;
  children: OrgChartNode[];
}

export interface OrgChartResponse {
  data: OrgChartNode[];
  message: string;
}

// ── Department Types ───────────────────────────────────────────────

export interface DepartmentDetail {
  id: string;
  keka_id: string | null;
  name: string;
  code: string | null;
  description: string | null;
  parent_department_id: string | null;
  head_employee_id: string | null;
  location_id: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  employee_count: number;
  location: { id: string; name: string; city: string | null } | null;
  head_employee_name: string | null;
}

export interface DepartmentListResponse {
  data: DepartmentDetail[];
  message: string;
}

export interface DepartmentMembersResponse {
  data: EmployeeListItem[];
  meta: PaginationMeta;
  message: string;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function getOrgChart(params?: {
  root_id?: string;
  max_depth?: number;
}): Promise<OrgChartResponse> {
  const { data } = await apiClient.get("/employees/org-chart", { params });
  return data;
}

export async function getDepartmentsList(): Promise<DepartmentListResponse> {
  const { data } = await apiClient.get("/departments");
  return data;
}

export async function getDepartmentDetail(id: string): Promise<{ data: DepartmentDetail; message: string }> {
  const { data } = await apiClient.get(`/departments/${id}`);
  return data;
}

export async function getDepartmentMembers(
  id: string,
  params?: {
    search?: string;
    employment_status?: string;
    page?: number;
    page_size?: number;
  }
): Promise<DepartmentMembersResponse> {
  const { data } = await apiClient.get(`/departments/${id}/members`, { params });
  return data;
}
