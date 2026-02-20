/**
 * DashboardPage — HR Intelligence command centre.
 *
 * Features:
 *  • Summary KPI cards (total employees, present today, on leave, pending approvals)
 *  • Attendance trend area chart (7 / 30 day toggle)
 *  • Department headcount horizontal bar chart
 *  • Upcoming birthdays list
 *  • Recent activities feed
 *  • Quick-access widgets for Salary, Leave summary, New Joiners
 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import {
  Users,
  UserCheck,
  CalendarOff,
  ClipboardCheck,
  TrendingUp,
  Building2,
  Cake,
  Activity,
  Loader2,
  AlertCircle,
  Banknote,
  Calendar,
  UserPlus,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { cn, getInitials, formatDate } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import * as dashboardApi from "@/api/dashboard";
import * as salaryApi from "@/api/salary";

// ── Helpers ────────────────────────────────────────────────────────

function formatShortDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  } catch {
    return dateStr;
  }
}

function timeAgo(dateStr: string): string {
  try {
    const now = new Date();
    const then = new Date(dateStr);
    if (isNaN(then.getTime())) return dateStr;
    const diffMs = now.getTime() - then.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return "just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay === 1) return "yesterday";
    if (diffDay < 7) return `${diffDay}d ago`;
    return formatDate(dateStr);
  } catch {
    return dateStr;
  }
}

const ACTION_ICONS: Record<string, string> = {
  create: "🆕",
  update: "✏️",
  approve: "✅",
  reject: "❌",
  cancel: "🚫",
  delete: "🗑️",
};

// ── Stat Card Config ───────────────────────────────────────────────

interface StatCardConfig {
  key: keyof dashboardApi.DashboardSummary;
  label: string;
  icon: typeof Users;
  color: string;
  bg: string;
}

const STAT_CARDS: StatCardConfig[] = [
  {
    key: "total_employees",
    label: "Total Employees",
    icon: Users,
    color: "text-violet-600",
    bg: "bg-violet-50",
  },
  {
    key: "present_today",
    label: "Present Today",
    icon: UserCheck,
    color: "text-emerald-600",
    bg: "bg-emerald-50",
  },
  {
    key: "on_leave_today",
    label: "On Leave",
    icon: CalendarOff,
    color: "text-amber-600",
    bg: "bg-amber-50",
  },
  {
    key: "pending_approvals",
    label: "Pending Approvals",
    icon: ClipboardCheck,
    color: "text-blue-600",
    bg: "bg-blue-50",
  },
];

// ── Attendance Trend Chart Colors ──────────────────────────────────

const TREND_COLORS = {
  present: "#22c55e",
  absent: "#ef4444",
  on_leave: "#3b82f6",
  work_from_home: "#14b8a6",
  half_day: "#f59e0b",
};

// ── Component ──────────────────────────────────────────────────────

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [trendPeriod, setTrendPeriod] = useState<7 | 30>(7);

  // ── Queries ────────────────────────────────────────────────────

  const summaryQuery = useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: dashboardApi.getDashboardSummary,
    staleTime: 2 * 60 * 1000,
  });

  const trendQuery = useQuery({
    queryKey: ["dashboard", "attendance-trend", trendPeriod],
    queryFn: () => dashboardApi.getAttendanceTrend(trendPeriod),
    staleTime: 2 * 60 * 1000,
  });

  const headcountQuery = useQuery({
    queryKey: ["dashboard", "department-headcount"],
    queryFn: dashboardApi.getDepartmentHeadcount,
    staleTime: 5 * 60 * 1000,
  });

  const birthdaysQuery = useQuery({
    queryKey: ["dashboard", "birthdays"],
    queryFn: () => dashboardApi.getUpcomingBirthdays(30),
    staleTime: 10 * 60 * 1000,
  });

  const activitiesQuery = useQuery({
    queryKey: ["dashboard", "recent-activities"],
    queryFn: () => dashboardApi.getRecentActivities(15),
    staleTime: 1 * 60 * 1000,
  });

  const salarySummaryQuery = useQuery({
    queryKey: ["dashboard", "salary-summary"],
    queryFn: salaryApi.getSalarySummary,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const leaveSummaryQuery = useQuery({
    queryKey: ["dashboard", "leave-summary"],
    queryFn: dashboardApi.getLeaveSummary,
    staleTime: 5 * 60 * 1000,
    retry: 1,
  });

  const newJoinersQuery = useQuery({
    queryKey: ["dashboard", "new-joiners"],
    queryFn: dashboardApi.getNewJoiners,
    staleTime: 10 * 60 * 1000,
    retry: 1,
  });

  // ── Render ─────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">
          Welcome back, {user?.display_name?.split(" ")[0] || "there"}!
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Here's what's happening at Creativefuel today
        </p>
      </div>

      {/* ── Summary Cards ─────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map((stat) => {
          const Icon = stat.icon;
          const value = summaryQuery.data?.[stat.key];
          const isLoading = summaryQuery.isLoading;

          return (
            <Card key={stat.key} className="py-0">
              <CardContent className="flex items-center gap-4 p-5">
                <div className={cn("rounded-xl p-3", stat.bg)}>
                  <Icon className={cn("h-5 w-5", stat.color)} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-muted-foreground">
                    {stat.label}
                  </p>
                  {isLoading ? (
                    <div className="mt-1 h-7 w-12 animate-pulse rounded bg-muted" />
                  ) : summaryQuery.isError ? (
                    <p className="text-sm text-muted-foreground">—</p>
                  ) : (
                    <p className="text-2xl font-bold text-foreground">
                      {value?.toLocaleString("en-IN") ?? "—"}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* ── Charts Row ────────────────────────────────────────────── */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Attendance Trend — spans 2 cols */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                <CardTitle className="text-base">Attendance Trend</CardTitle>
              </div>
              <div className="flex gap-1">
                <Button
                  variant={trendPeriod === 7 ? "default" : "outline"}
                  size="xs"
                  onClick={() => setTrendPeriod(7)}
                >
                  7 days
                </Button>
                <Button
                  variant={trendPeriod === 30 ? "default" : "outline"}
                  size="xs"
                  onClick={() => setTrendPeriod(30)}
                >
                  30 days
                </Button>
              </div>
            </div>
            {trendQuery.data?.averages && (
              <CardDescription>
                Avg attendance rate:{" "}
                <span className="font-medium text-foreground">
                  {trendQuery.data.averages.avg_attendance_rate}%
                </span>
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {trendQuery.isLoading ? (
              <LoadingPlaceholder height="h-[280px]" />
            ) : trendQuery.isError ? (
              <ErrorPlaceholder
                message="Failed to load attendance trend"
                height="h-[280px]"
              />
            ) : (trendQuery.data?.data ?? []).length === 0 ? (
              <EmptyPlaceholder
                message="No attendance trend data available"
                height="h-[280px]"
              />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart
                  data={trendQuery.data?.data ?? []}
                  margin={{ top: 5, right: 10, left: -10, bottom: 0 }}
                >
                  <defs>
                    <linearGradient
                      id="gradPresent"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor={TREND_COLORS.present}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor={TREND_COLORS.present}
                        stopOpacity={0}
                      />
                    </linearGradient>
                    <linearGradient
                      id="gradAbsent"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor={TREND_COLORS.absent}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor={TREND_COLORS.absent}
                        stopOpacity={0}
                      />
                    </linearGradient>
                    <linearGradient
                      id="gradLeave"
                      x1="0"
                      y1="0"
                      x2="0"
                      y2="1"
                    >
                      <stop
                        offset="5%"
                        stopColor={TREND_COLORS.on_leave}
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor={TREND_COLORS.on_leave}
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    vertical={false}
                    stroke="#e2e8f0"
                  />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatShortDate}
                    tick={{ fontSize: 12, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 12, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip
                    labelFormatter={(label) => formatShortDate(label as string)}
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid #e2e8f0",
                      fontSize: "13px",
                    }}
                  />
                  <Legend
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ fontSize: "12px", paddingTop: "8px" }}
                  />
                  <Area
                    type="monotone"
                    dataKey="present"
                    name="Present"
                    stroke={TREND_COLORS.present}
                    fill="url(#gradPresent)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="absent"
                    name="Absent"
                    stroke={TREND_COLORS.absent}
                    fill="url(#gradAbsent)"
                    strokeWidth={2}
                  />
                  <Area
                    type="monotone"
                    dataKey="on_leave"
                    name="On Leave"
                    stroke={TREND_COLORS.on_leave}
                    fill="url(#gradLeave)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Department Headcount */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">Department Headcount</CardTitle>
            </div>
            {headcountQuery.data && (
              <CardDescription>
                {headcountQuery.data.total_departments ?? 0} departments
              </CardDescription>
            )}
          </CardHeader>
          <CardContent>
            {headcountQuery.isLoading ? (
              <LoadingPlaceholder height="h-[280px]" />
            ) : headcountQuery.isError ? (
              <ErrorPlaceholder
                message="Failed to load headcount"
                height="h-[280px]"
              />
            ) : (headcountQuery.data?.data ?? []).length === 0 ? (
              <EmptyPlaceholder
                message="No department data available"
                height="h-[280px]"
              />
            ) : (
              <ResponsiveContainer width="100%" height={280}>
                <BarChart
                  data={headcountQuery.data?.data ?? []}
                  layout="vertical"
                  margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    horizontal={false}
                    stroke="#e2e8f0"
                  />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    type="category"
                    dataKey="department_name"
                    width={90}
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <RechartsTooltip
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid #e2e8f0",
                      fontSize: "13px",
                    }}
                  />
                  <Bar
                    dataKey="headcount"
                    name="Headcount"
                    fill="#6C5CE7"
                    radius={[0, 4, 4, 0]}
                    barSize={18}
                  />
                  <Bar
                    dataKey="present_today"
                    name="Present"
                    fill="#22c55e"
                    radius={[0, 4, 4, 0]}
                    barSize={18}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Quick Access: Salary, Leave Summary, New Joiners ──────── */}
      <div className="grid gap-4 sm:grid-cols-3">
        {/* Salary Summary Widget */}
        <Card
          className="cursor-pointer transition-all hover:shadow-md"
          onClick={() => navigate(ROUTES.SALARY)}
        >
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="rounded-xl bg-emerald-50 p-2.5">
                <Banknote className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Salary</p>
                <p className="text-xs text-muted-foreground">Last month</p>
              </div>
            </div>
            {salarySummaryQuery.isLoading ? (
              <div className="h-12 animate-pulse rounded bg-muted" />
            ) : salarySummaryQuery.isError ? (
              <p className="text-sm text-muted-foreground">No salary data available</p>
            ) : salarySummaryQuery.data ? (
              <div>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {formatCurrency(salarySummaryQuery.data?.last_month_net ?? 0)}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {salarySummaryQuery.data?.last_month_label ?? ""}
                  {salarySummaryQuery.data?.next_payroll_date && (
                    <span className="ml-2">
                      · Next payroll:{" "}
                      <span className="font-medium text-foreground">
                        {formatShortDate(salarySummaryQuery.data.next_payroll_date)}
                      </span>
                    </span>
                  )}
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">—</p>
            )}
          </CardContent>
        </Card>

        {/* Leave Summary Widget */}
        <Card
          className="cursor-pointer transition-all hover:shadow-md"
          onClick={() => navigate(ROUTES.LEAVE)}
        >
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="rounded-xl bg-blue-50 p-2.5">
                <Calendar className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">Leave</p>
                <p className="text-xs text-muted-foreground">Summary</p>
              </div>
            </div>
            {leaveSummaryQuery.isLoading ? (
              <div className="h-12 animate-pulse rounded bg-muted" />
            ) : leaveSummaryQuery.isError ? (
              <p className="text-sm text-muted-foreground">No leave data available</p>
            ) : (leaveSummaryQuery.data?.data ?? []).length > 0 ? (
              <div className="space-y-1">
                {(leaveSummaryQuery.data?.data ?? []).slice(0, 3).map((item) => (
                  <div key={item.leave_type_code} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{item.leave_type_code}</span>
                    <span className="font-medium text-foreground">
                      {item.total_used} used
                      {item.total_pending > 0 && (
                        <span className="ml-1 text-amber-600">({item.total_pending} pending)</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">—</p>
            )}
          </CardContent>
        </Card>

        {/* New Joiners Widget */}
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-3 mb-3">
              <div className="rounded-xl bg-violet-50 p-2.5">
                <UserPlus className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">New Joiners</p>
                <p className="text-xs text-muted-foreground">This month</p>
              </div>
            </div>
            {newJoinersQuery.isLoading ? (
              <div className="h-12 animate-pulse rounded bg-muted" />
            ) : newJoinersQuery.isError ? (
              <p className="text-sm text-muted-foreground">No data available</p>
            ) : (newJoinersQuery.data?.data ?? []).length > 0 ? (
              <div>
                <p className="text-2xl font-bold tabular-nums text-foreground">
                  {(newJoinersQuery.data?.data ?? []).length}
                </p>
                <div className="mt-2 space-y-1">
                  {(newJoinersQuery.data?.data ?? []).slice(0, 2).map((joiner) => (
                    <p key={joiner.employee_id} className="text-xs text-muted-foreground truncate">
                      {joiner.display_name ?? joiner.employee_code}
                      {joiner.department_name && ` · ${joiner.department_name}`}
                    </p>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No new joiners this month</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ── Bottom Row: Birthdays + Activity Feed ─────────────────── */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Upcoming Birthdays */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Cake className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">Upcoming Birthdays</CardTitle>
            </div>
            <CardDescription>Next 30 days</CardDescription>
          </CardHeader>
          <CardContent>
            {birthdaysQuery.isLoading ? (
              <LoadingPlaceholder height="h-[240px]" />
            ) : birthdaysQuery.isError ? (
              <ErrorPlaceholder
                message="Failed to load birthdays"
                height="h-[240px]"
              />
            ) : !(birthdaysQuery.data?.data ?? []).length ? (
              <div className="flex h-[240px] flex-col items-center justify-center text-muted-foreground">
                <Cake className="mb-2 h-8 w-8 opacity-40" />
                <p className="text-sm">No upcoming birthdays</p>
              </div>
            ) : (
              <div className="max-h-[280px] space-y-3 overflow-y-auto pr-1">
                {(birthdaysQuery.data?.data ?? []).map((person) => (
                  <div
                    key={person.employee_id}
                    className="flex items-center gap-3 rounded-lg border border-transparent p-2 transition-colors hover:border-border hover:bg-muted/50"
                  >
                    <Avatar size="default">
                      {person.profile_photo_url ? (
                        <AvatarImage
                          src={person.profile_photo_url}
                          alt={person.display_name ?? ""}
                        />
                      ) : null}
                      <AvatarFallback>
                        {getInitials(person.display_name ?? person.employee_code)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-foreground">
                        {person.display_name ?? person.employee_code}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {person.department_name ?? "—"}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-foreground">
                        {formatShortDate(person.birthday_date)}
                      </p>
                      <Badge
                        variant={
                          person.days_away === 0 ? "default" : "secondary"
                        }
                        className={cn(
                          "text-[10px]",
                          person.days_away === 0 &&
                            "bg-emerald-500 text-white"
                        )}
                      >
                        {person.days_away === 0
                          ? "🎉 Today!"
                          : person.days_away === 1
                            ? "Tomorrow"
                            : `${person.days_away}d away`}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Activities */}
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">Recent Activity</CardTitle>
            </div>
            <CardDescription>Latest platform events</CardDescription>
          </CardHeader>
          <CardContent>
            {activitiesQuery.isLoading ? (
              <LoadingPlaceholder height="h-[240px]" />
            ) : activitiesQuery.isError ? (
              <ErrorPlaceholder
                message="Failed to load activities"
                height="h-[240px]"
              />
            ) : !(activitiesQuery.data?.data ?? []).length ? (
              <div className="flex h-[240px] flex-col items-center justify-center text-muted-foreground">
                <Activity className="mb-2 h-8 w-8 opacity-40" />
                <p className="text-sm">No recent activity</p>
              </div>
            ) : (
              <div className="max-h-[280px] space-y-1 overflow-y-auto pr-1">
                {(activitiesQuery.data?.data ?? []).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-start gap-3 rounded-lg p-2 transition-colors hover:bg-muted/50"
                  >
                    <span className="mt-0.5 text-base leading-none">
                      {ACTION_ICONS[item.action] ?? "📋"}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-foreground">
                        {item.description}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {timeAgo(item.created_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ── Shared Micro-Components ────────────────────────────────────────

function LoadingPlaceholder({ height = "h-[200px]" }: { height?: string }) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-lg bg-muted/30",
        height
      )}
    >
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  );
}

function ErrorPlaceholder({
  message,
  height = "h-[200px]",
}: {
  message: string;
  height?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg bg-red-50/50",
        height
      )}
    >
      <AlertCircle className="h-5 w-5 text-red-400" />
      <p className="text-sm text-red-500">{message}</p>
    </div>
  );
}

function EmptyPlaceholder({
  message,
  height = "h-[200px]",
}: {
  message: string;
  height?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg bg-muted/20",
        height
      )}
    >
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
