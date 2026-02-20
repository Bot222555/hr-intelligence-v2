/**
 * Employees API module — employee directory, departments, and locations
 * for the Employee Directory page.
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

export async function getDepartments(): Promise<{ data: Department[]; message: string }> {
  const { data } = await apiClient.get("/departments");
  return data;
}

export async function getLocations(): Promise<{ data: Location[]; message: string }> {
  const { data } = await apiClient.get("/locations");
  return data;
}
