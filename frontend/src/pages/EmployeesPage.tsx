/**
 * EmployeesPage — Searchable employee directory with grid/list view.
 *
 * Features:
 *  • Search by name, email, or employee code
 *  • Filter by department and location
 *  • Toggle between grid (card) and list (table) views
 *  • Paginated with page navigation
 *  • Avatar with fallback initials, department badge, status indicator
 */

import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Search,
  LayoutGrid,
  List,
  ChevronLeft,
  ChevronRight,
  Users,
  MapPin,
  Building2,
  Mail,
  Loader2,
  AlertCircle,
  X,
} from "lucide-react";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { cn, getInitials } from "@/lib/utils";
import * as employeesApi from "@/api/employees";

// ── Constants ──────────────────────────────────────────────────────

const PAGE_SIZE = 24;

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  active: { label: "Active", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  notice_period: { label: "Notice Period", className: "bg-amber-50 text-amber-700 border-amber-200" },
  relieved: { label: "Relieved", className: "bg-slate-50 text-slate-600 border-slate-200" },
  absconding: { label: "Absconding", className: "bg-red-50 text-red-600 border-red-200" },
};

// ── Component ──────────────────────────────────────────────────────

export function EmployeesPage() {
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [departmentId, setDepartmentId] = useState<string>("");
  const [locationId, setLocationId] = useState<string>("");
  const [page, setPage] = useState(1);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Reset page when filters change
  useEffect(() => {
    setPage(1);
  }, [departmentId, locationId]);

  // ── Queries ────────────────────────────────────────────────────

  const employeesQuery = useQuery({
    queryKey: [
      "employees",
      debouncedSearch,
      departmentId,
      locationId,
      page,
    ],
    queryFn: () =>
      employeesApi.getEmployees({
        search: debouncedSearch || undefined,
        department_id: departmentId || undefined,
        location_id: locationId || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    staleTime: 2 * 60 * 1000,
    placeholderData: (prev) => prev,
  });

  const departmentsQuery = useQuery({
    queryKey: ["departments"],
    queryFn: employeesApi.getDepartments,
    staleTime: 10 * 60 * 1000,
  });

  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: employeesApi.getLocations,
    staleTime: 10 * 60 * 1000,
  });

  // ── Derived State ──────────────────────────────────────────────

  const employees = employeesQuery.data?.data ?? [];
  const meta = employeesQuery.data?.meta;
  const departments = departmentsQuery.data?.data ?? [];
  const locations = locationsQuery.data?.data ?? [];
  const hasActiveFilters = !!debouncedSearch || !!departmentId || !!locationId;

  const clearFilters = useCallback(() => {
    setSearch("");
    setDebouncedSearch("");
    setDepartmentId("");
    setLocationId("");
    setPage(1);
  }, []);

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">
            Employee Directory
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {meta
              ? `${meta.total.toLocaleString("en-IN")} employee${meta.total !== 1 ? "s" : ""}`
              : "Browse and search employees"}
          </p>
        </div>
        <div className="flex gap-1 rounded-lg border border-border p-1">
          <Button
            variant={viewMode === "grid" ? "default" : "ghost"}
            size="icon-sm"
            onClick={() => setViewMode("grid")}
            aria-label="Grid view"
          >
            <LayoutGrid className="h-4 w-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "default" : "ghost"}
            size="icon-sm"
            onClick={() => setViewMode("list")}
            aria-label="List view"
          >
            <List className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Filters Bar */}
      <Card className="py-0">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
            {/* Search */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search by name, email, or employee code…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>

            {/* Department Filter */}
            <div className="relative">
              <Building2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <select
                value={departmentId}
                onChange={(e) => setDepartmentId(e.target.value)}
                className="h-9 w-full min-w-[160px] appearance-none rounded-md border border-input bg-transparent py-1 pl-9 pr-8 text-sm text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:w-auto"
              >
                <option value="">All Departments</option>
                {departments.map((dept) => (
                  <option key={dept.id} value={dept.id}>
                    {dept.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Location Filter */}
            <div className="relative">
              <MapPin className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <select
                value={locationId}
                onChange={(e) => setLocationId(e.target.value)}
                className="h-9 w-full min-w-[140px] appearance-none rounded-md border border-input bg-transparent py-1 pl-9 pr-8 text-sm text-foreground shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 sm:w-auto"
              >
                <option value="">All Locations</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Clear Filters */}
            {hasActiveFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={clearFilters}
                className="gap-1 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
                Clear
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Content */}
      {employeesQuery.isLoading && !employeesQuery.data ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : employeesQuery.isError ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="h-10 w-10 text-red-400" />
            <h3 className="mt-3 text-lg font-medium text-foreground">
              Failed to load employees
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Please try refreshing the page
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => employeesQuery.refetch()}
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : employees.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Users className="h-10 w-10 text-muted-foreground/40" />
            <h3 className="mt-3 text-lg font-medium text-foreground">
              No employees found
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {hasActiveFilters
                ? "Try adjusting your search or filters"
                : "No employees in the directory yet"}
            </p>
            {hasActiveFilters && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={clearFilters}
              >
                Clear all filters
              </Button>
            )}
          </CardContent>
        </Card>
      ) : viewMode === "grid" ? (
        /* ── Grid View ──────────────────────────────────────────── */
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {employees.map((emp) => (
            <EmployeeCard key={emp.id} employee={emp} />
          ))}
        </div>
      ) : (
        /* ── List View ──────────────────────────────────────────── */
        <Card className="overflow-hidden py-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Employee
                  </th>
                  <th className="hidden px-4 py-3 text-left font-medium text-muted-foreground md:table-cell">
                    Designation
                  </th>
                  <th className="hidden px-4 py-3 text-left font-medium text-muted-foreground sm:table-cell">
                    Department
                  </th>
                  <th className="hidden px-4 py-3 text-left font-medium text-muted-foreground lg:table-cell">
                    Location
                  </th>
                  <th className="hidden px-4 py-3 text-left font-medium text-muted-foreground xl:table-cell">
                    Email
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <EmployeeRow key={emp.id} employee={emp} />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Pagination */}
      {meta && meta.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Showing{" "}
            <span className="font-medium text-foreground">
              {(meta.page - 1) * meta.page_size + 1}
            </span>
            –
            <span className="font-medium text-foreground">
              {Math.min(meta.page * meta.page_size, meta.total)}
            </span>{" "}
            of{" "}
            <span className="font-medium text-foreground">
              {meta.total.toLocaleString("en-IN")}
            </span>
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!meta.has_prev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
              Previous
            </Button>
            {/* Page numbers */}
            <div className="hidden items-center gap-1 sm:flex">
              {generatePageNumbers(meta.page, meta.total_pages).map(
                (pageNum, idx) =>
                  pageNum === -1 ? (
                    <span
                      key={`ellipsis-${idx}`}
                      className="px-1 text-muted-foreground"
                    >
                      …
                    </span>
                  ) : (
                    <Button
                      key={pageNum}
                      variant={pageNum === meta.page ? "default" : "outline"}
                      size="icon-sm"
                      onClick={() => setPage(pageNum)}
                    >
                      {pageNum}
                    </Button>
                  )
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={!meta.has_next}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Employee Card (Grid View) ──────────────────────────────────────

function EmployeeCard({
  employee,
}: {
  employee: employeesApi.EmployeeListItem;
}) {
  const displayName =
    employee.display_name || `${employee.first_name} ${employee.last_name}`;
  const status = STATUS_STYLES[employee.employment_status] ??
    STATUS_STYLES.active;

  return (
    <Card className="group py-0 transition-shadow hover:shadow-md">
      <CardContent className="p-5">
        <div className="flex flex-col items-center text-center">
          {/* Avatar */}
          <Avatar size="lg" className="h-16 w-16">
            {employee.profile_photo_url ? (
              <AvatarImage
                src={employee.profile_photo_url}
                alt={displayName}
              />
            ) : null}
            <AvatarFallback className="text-base font-medium">
              {getInitials(displayName)}
            </AvatarFallback>
          </Avatar>

          {/* Name & Designation */}
          <h3 className="mt-3 truncate text-sm font-semibold text-foreground w-full">
            {displayName}
          </h3>
          <p className="mt-0.5 truncate text-xs text-muted-foreground w-full">
            {employee.designation || employee.job_title || "—"}
          </p>

          {/* Department & Location */}
          <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
            {employee.department && (
              <Badge variant="secondary" className="text-[10px] font-normal">
                {employee.department.name}
              </Badge>
            )}
            {employee.location && (
              <Badge variant="outline" className="text-[10px] font-normal gap-0.5">
                <MapPin className="h-2.5 w-2.5" />
                {employee.location.name}
              </Badge>
            )}
          </div>

          {/* Email */}
          <a
            href={`mailto:${employee.email}`}
            className="mt-2.5 flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-primary"
            title={employee.email}
          >
            <Mail className="h-3 w-3" />
            <span className="max-w-[180px] truncate">{employee.email}</span>
          </a>

          {/* Status */}
          <Badge
            variant="outline"
            className={cn("mt-3 text-[10px] border", status.className)}
          >
            {status.label}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Employee Row (List View) ───────────────────────────────────────

function EmployeeRow({
  employee,
}: {
  employee: employeesApi.EmployeeListItem;
}) {
  const displayName =
    employee.display_name || `${employee.first_name} ${employee.last_name}`;
  const status = STATUS_STYLES[employee.employment_status] ??
    STATUS_STYLES.active;

  return (
    <tr className="border-b transition-colors hover:bg-muted/50 last:border-0">
      {/* Employee */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <Avatar size="default">
            {employee.profile_photo_url ? (
              <AvatarImage
                src={employee.profile_photo_url}
                alt={displayName}
              />
            ) : null}
            <AvatarFallback className="text-xs">
              {getInitials(displayName)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-foreground">
              {displayName}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {employee.employee_code}
            </p>
          </div>
        </div>
      </td>

      {/* Designation */}
      <td className="hidden px-4 py-3 md:table-cell">
        <p className="truncate text-sm text-foreground">
          {employee.designation || employee.job_title || "—"}
        </p>
      </td>

      {/* Department */}
      <td className="hidden px-4 py-3 sm:table-cell">
        {employee.department ? (
          <Badge variant="secondary" className="text-xs font-normal">
            {employee.department.name}
          </Badge>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </td>

      {/* Location */}
      <td className="hidden px-4 py-3 lg:table-cell">
        {employee.location ? (
          <span className="flex items-center gap-1 text-sm text-foreground">
            <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
            {employee.location.name}
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
        )}
      </td>

      {/* Email */}
      <td className="hidden px-4 py-3 xl:table-cell">
        <a
          href={`mailto:${employee.email}`}
          className="text-sm text-muted-foreground transition-colors hover:text-primary"
        >
          {employee.email}
        </a>
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <Badge
          variant="outline"
          className={cn("text-[10px] border", status.className)}
        >
          {status.label}
        </Badge>
      </td>
    </tr>
  );
}

// ── Helpers ────────────────────────────────────────────────────────

/**
 * Generate page numbers with ellipsis for pagination.
 * Returns page numbers or -1 for ellipsis.
 */
function generatePageNumbers(
  current: number,
  total: number,
): number[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: number[] = [];
  pages.push(1);

  if (current > 3) {
    pages.push(-1); // ellipsis
  }

  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    pages.push(i);
  }

  if (current < total - 2) {
    pages.push(-1); // ellipsis
  }

  pages.push(total);

  return pages;
}
