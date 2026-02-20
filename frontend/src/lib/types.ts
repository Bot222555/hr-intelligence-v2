// ── User & Auth ──────────────────────────────────────────────

export interface Department {
  id: string;
  name: string;
}

export interface Location {
  id: string;
  name: string;
}

export interface User {
  id: string;
  employee_number: string;
  display_name: string;
  email: string;
  role: UserRole;
  permissions: string[];
  profile_picture_url: string | null;
  department: Department | null;
  location: Location | null;
  direct_reports_count: number;
}

export type UserRole = "employee" | "manager" | "hr_admin" | "system_admin";

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface GoogleLoginRequest {
  code: string;
  redirect_uri: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

// ── API Responses ────────────────────────────────────────────

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PaginatedResponse<T> {
  data: T[];
  meta: PaginationMeta;
}

export interface ApiError {
  type: string;
  title: string;
  status: number;
  detail: string;
  errors?: Record<string, string[]>;
}

// ── Navigation ───────────────────────────────────────────────

export interface NavItem {
  label: string;
  path: string;
  icon: string;
  permissions?: string[];
  roles?: UserRole[];
}
