/**
 * TeamAttendancePage — Manager / HR view of today's team attendance.
 *
 * Features:
 *  • Summary cards (total, present, absent, on leave, WFH)
 *  • Filterable table: department, location, status
 *  • Employee rows with avatar, status badge, clock times, hours
 *  • Search by employee name
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Users,
  Search,
  Filter,
  XCircle,
  Clock,
  Home,
  UserCheck,
  ChevronDown,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn, getInitials, formatTime } from "@/lib/utils";
import * as attendanceApi from "@/api/attendance";
import type {
  AttendanceStatus,
  TodayAttendanceItem,
} from "@/api/attendance";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  { label: string; dot: string; badgeBg: string; badgeText: string }
> = {
  present: {
    label: "Present",
    dot: "bg-emerald-500",
    badgeBg: "bg-emerald-50 border-emerald-200",
    badgeText: "text-emerald-700",
  },
  absent: {
    label: "Absent",
    dot: "bg-red-500",
    badgeBg: "bg-red-50 border-red-200",
    badgeText: "text-red-700",
  },
  half_day: {
    label: "Half Day",
    dot: "bg-amber-500",
    badgeBg: "bg-amber-50 border-amber-200",
    badgeText: "text-amber-700",
  },
  on_leave: {
    label: "On Leave",
    dot: "bg-blue-500",
    badgeBg: "bg-blue-50 border-blue-200",
    badgeText: "text-blue-700",
  },
  work_from_home: {
    label: "WFH",
    dot: "bg-teal-500",
    badgeBg: "bg-teal-50 border-teal-200",
    badgeText: "text-teal-700",
  },
  on_duty: {
    label: "On Duty",
    dot: "bg-indigo-500",
    badgeBg: "bg-indigo-50 border-indigo-200",
    badgeText: "text-indigo-700",
  },
  weekend: {
    label: "Weekend",
    dot: "bg-slate-400",
    badgeBg: "bg-slate-50 border-slate-200",
    badgeText: "text-slate-600",
  },
  holiday: {
    label: "Holiday",
    dot: "bg-slate-500",
    badgeBg: "bg-slate-100 border-slate-300",
    badgeText: "text-slate-700",
  },
};

const ARRIVAL_LABELS: Record<string, { label: string; color: string }> = {
  on_time: { label: "On Time", color: "text-emerald-600" },
  late: { label: "Late", color: "text-amber-600" },
  very_late: { label: "Very Late", color: "text-red-600" },
};

// ── Component ──────────────────────────────────────────────────────

export function TeamAttendancePage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<AttendanceStatus | "all">("all");
  const [deptFilter, setDeptFilter] = useState<string>("all");
  const [showFilters, setShowFilters] = useState(false);

  // ── Data fetching ────────────────────────────────────────────────

  const { data: todayData, isLoading } = useQuery({
    queryKey: ["todayAttendance"],
    queryFn: () => attendanceApi.getTodayAttendance(),
    refetchInterval: 60_000, // Refresh every minute
  });

  // ── Filtered data ────────────────────────────────────────────────

  const filteredItems = useMemo(() => {
    if (!todayData?.data) return [];

    return todayData.data.filter((item: TodayAttendanceItem) => {
      // Status filter
      if (statusFilter !== "all" && item.status !== statusFilter) return false;

      // Department filter
      if (
        deptFilter !== "all" &&
        item.employee.department_name !== deptFilter
      )
        return false;

      // Search
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const name = (item.employee.display_name ?? "").toLowerCase();
        const code = item.employee.employee_code.toLowerCase();
        const dept = (item.employee.department_name ?? "").toLowerCase();
        if (!name.includes(q) && !code.includes(q) && !dept.includes(q))
          return false;
      }

      return true;
    });
  }, [todayData, statusFilter, deptFilter, searchQuery]);

  // Unique departments from data
  const uniqueDepts = useMemo(() => {
    if (!todayData?.data) return [];
    const set = new Set<string>();
    todayData.data.forEach((item: TodayAttendanceItem) => {
      if (item.employee.department_name) set.add(item.employee.department_name);
    });
    return Array.from(set).sort();
  }, [todayData]);

  const summary = todayData?.summary;

  // ── Render ───────────────────────────────────────────────────────

  const todayLabel = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Team Attendance</h2>
        <p className="mt-1 text-sm text-muted-foreground">{todayLabel}</p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        <SummaryCard
          icon={<Users className="h-5 w-5 text-primary" />}
          label="Total"
          value={summary?.total_employees ?? 0}
          bg="bg-primary/5"
        />
        <SummaryCard
          icon={<UserCheck className="h-5 w-5 text-emerald-600" />}
          label="Present"
          value={summary?.present ?? 0}
          bg="bg-emerald-50"
        />
        <SummaryCard
          icon={<XCircle className="h-5 w-5 text-red-500" />}
          label="Absent"
          value={summary?.absent ?? 0}
          bg="bg-red-50"
        />
        <SummaryCard
          icon={<Clock className="h-5 w-5 text-blue-500" />}
          label="On Leave"
          value={summary?.on_leave ?? 0}
          bg="bg-blue-50"
        />
        <SummaryCard
          icon={<Home className="h-5 w-5 text-teal-500" />}
          label="WFH"
          value={summary?.work_from_home ?? 0}
          bg="bg-teal-50"
        />
      </div>

      {/* Search & Filters */}
      <Card>
        <CardContent className="py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {/* Search */}
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search by name, code, or department…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-9 w-full rounded-lg border border-input bg-background pl-9 pr-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
              />
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowFilters(!showFilters)}
                className="gap-1.5"
              >
                <Filter className="h-3.5 w-3.5" />
                Filters
                <ChevronDown
                  className={cn(
                    "h-3.5 w-3.5 transition-transform",
                    showFilters && "rotate-180",
                  )}
                />
              </Button>

              <span className="text-xs text-muted-foreground">
                {filteredItems.length} of {todayData?.data.length ?? 0} employees
              </span>
            </div>
          </div>

          {/* Expanded filters */}
          {showFilters && (
            <div className="mt-3 flex flex-wrap gap-3 border-t border-border pt-3">
              {/* Status filter */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Status
                </label>
                <select
                  value={statusFilter}
                  onChange={(e) =>
                    setStatusFilter(e.target.value as AttendanceStatus | "all")
                  }
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                >
                  <option value="all">All Statuses</option>
                  <option value="present">Present</option>
                  <option value="absent">Absent</option>
                  <option value="half_day">Half Day</option>
                  <option value="on_leave">On Leave</option>
                  <option value="work_from_home">WFH</option>
                  <option value="on_duty">On Duty</option>
                </select>
              </div>

              {/* Department filter */}
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Department
                </label>
                <select
                  value={deptFilter}
                  onChange={(e) => setDeptFilter(e.target.value)}
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm outline-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                >
                  <option value="all">All Departments</option>
                  {uniqueDepts.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
              </div>

              {/* Clear filters */}
              {(statusFilter !== "all" || deptFilter !== "all") && (
                <div className="flex items-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setStatusFilter("all");
                      setDeptFilter("all");
                      setSearchQuery("");
                    }}
                    className="text-xs text-muted-foreground"
                  >
                    Clear Filters
                  </Button>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Attendance Table */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Users className="h-4 w-4 text-primary" />
            Team Members
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <Users className="h-10 w-10 text-muted-foreground/30" />
              <p className="mt-3 text-sm text-muted-foreground">
                {todayData?.data.length === 0
                  ? "No team members found"
                  : "No results match your filters"}
              </p>
            </div>
          ) : (
            <>
              {/* Desktop table */}
              <div className="hidden sm:block overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left">
                      <th className="pb-3 font-semibold text-muted-foreground">
                        Employee
                      </th>
                      <th className="pb-3 font-semibold text-muted-foreground">
                        Department
                      </th>
                      <th className="pb-3 font-semibold text-muted-foreground">
                        Status
                      </th>
                      <th className="pb-3 font-semibold text-muted-foreground">
                        Clock In
                      </th>
                      <th className="pb-3 font-semibold text-muted-foreground">
                        Clock Out
                      </th>
                      <th className="pb-3 font-semibold text-muted-foreground text-right">
                        Hours
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {filteredItems.map((item: TodayAttendanceItem) => {
                      const cfg = STATUS_CONFIG[item.status];
                      const arrival = item.arrival_status
                        ? ARRIVAL_LABELS[item.arrival_status]
                        : null;

                      return (
                        <tr
                          key={item.employee.id}
                          className="hover:bg-muted/50 transition-colors"
                        >
                          {/* Employee */}
                          <td className="py-3">
                            <div className="flex items-center gap-3">
                              <Avatar className="h-8 w-8">
                                <AvatarImage
                                  src={
                                    item.employee.profile_photo_url ?? undefined
                                  }
                                />
                                <AvatarFallback className="bg-primary/10 text-primary text-xs font-medium">
                                  {getInitials(
                                    item.employee.display_name || "?",
                                  )}
                                </AvatarFallback>
                              </Avatar>
                              <div>
                                <p className="font-medium text-foreground">
                                  {item.employee.display_name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                  {item.employee.employee_code}
                                  {item.employee.designation &&
                                    ` · ${item.employee.designation}`}
                                </p>
                              </div>
                            </div>
                          </td>

                          {/* Department */}
                          <td className="py-3 text-muted-foreground">
                            {item.employee.department_name || "—"}
                          </td>

                          {/* Status */}
                          <td className="py-3">
                            <div className="flex flex-col gap-1">
                              <Badge
                                className={cn(
                                  "border text-xs w-fit",
                                  cfg?.badgeBg,
                                  cfg?.badgeText,
                                )}
                              >
                                {cfg?.label || item.status}
                              </Badge>
                              {arrival && (
                                <span
                                  className={cn("text-[11px]", arrival.color)}
                                >
                                  {arrival.label}
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Clock In */}
                          <td className="py-3 tabular-nums text-muted-foreground">
                            {item.first_clock_in
                              ? formatTime(item.first_clock_in)
                              : "—"}
                          </td>

                          {/* Clock Out */}
                          <td className="py-3 tabular-nums text-muted-foreground">
                            {item.last_clock_out
                              ? formatTime(item.last_clock_out)
                              : "—"}
                          </td>

                          {/* Hours */}
                          <td className="py-3 text-right tabular-nums font-medium">
                            {item.total_hours != null
                              ? `${item.total_hours.toFixed(1)}h`
                              : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Mobile cards */}
              <div className="sm:hidden space-y-3">
                {filteredItems.map((item: TodayAttendanceItem) => {
                  const cfg = STATUS_CONFIG[item.status];
                  return (
                    <div
                      key={item.employee.id}
                      className="flex items-start gap-3 rounded-lg border border-border p-3"
                    >
                      <Avatar className="h-9 w-9 mt-0.5">
                        <AvatarImage
                          src={item.employee.profile_photo_url ?? undefined}
                        />
                        <AvatarFallback className="bg-primary/10 text-primary text-xs font-medium">
                          {getInitials(item.employee.display_name || "?")}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="font-medium text-foreground text-sm truncate">
                              {item.employee.display_name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {item.employee.department_name || item.employee.employee_code}
                            </p>
                          </div>
                          <Badge
                            className={cn(
                              "border text-[10px] shrink-0",
                              cfg?.badgeBg,
                              cfg?.badgeText,
                            )}
                          >
                            {cfg?.label || item.status}
                          </Badge>
                        </div>
                        <div className="mt-1.5 flex items-center gap-3 text-xs text-muted-foreground">
                          {item.first_clock_in && (
                            <span>In: {formatTime(item.first_clock_in)}</span>
                          )}
                          {item.last_clock_out && (
                            <span>Out: {formatTime(item.last_clock_out)}</span>
                          )}
                          {item.total_hours != null && (
                            <span className="font-medium text-foreground">
                              {item.total_hours.toFixed(1)}h
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Summary Card ───────────────────────────────────────────────────

function SummaryCard({
  icon,
  label,
  value,
  bg,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  bg: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className={cn("rounded-lg p-2", bg)}>{icon}</div>
        <div>
          <p className="text-2xl font-bold tabular-nums text-foreground">
            {value}
          </p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}
