export const APP_NAME = "HR Intelligence";
export const COMPANY_NAME = "Creativefuel";
export const APP_VERSION = "2.0.0";

export const ROUTES = {
  LOGIN: "/login",
  AUTH_CALLBACK: "/auth/callback",
  DASHBOARD: "/dashboard",
  EMPLOYEES: "/employees",
  ORG_CHART: "/org-chart",
  DEPARTMENTS: "/departments",
  ATTENDANCE: "/attendance",
  TEAM_ATTENDANCE: "/attendance/team",
  REGULARIZATION: "/attendance/regularization",
  LEAVE: "/leave",
  TEAM_LEAVE: "/leave/team",
  LEAVE_CALENDAR: "/leave/calendar",
  SALARY: "/salary",
  HELPDESK: "/helpdesk",
  EXPENSES: "/expenses",
  SETTINGS: "/settings",
} as const;

export const ROLES = {
  EMPLOYEE: "employee",
  MANAGER: "manager",
  HR_ADMIN: "hr_admin",
  SYSTEM_ADMIN: "system_admin",
} as const;

export const ADMIN_ROLES = [ROLES.HR_ADMIN, ROLES.SYSTEM_ADMIN] as const;

export const STORAGE_KEYS = {
  ACCESS_TOKEN: "hr_access_token",
  REFRESH_TOKEN: "hr_refresh_token",
} as const;
