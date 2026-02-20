/**
 * EmployeeProfilePage — Comprehensive employee profile with tabbed layout.
 *
 * Features:
 *  • Profile header with avatar, name, designation, department, employee code
 *  • Tab layout: Overview | Attendance | Leaves | Team
 *  • Overview: personal info + employment info cards, quick stats
 *  • Attendance: calendar heatmap + monthly stats
 *  • Leaves: balance cards per type + request history table
 *  • Team: direct reports grid (shown only for managers)
 */

import { useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Mail,
  Phone,
  MapPin,
  Building2,
  Clock,
  AlertTriangle,
  CheckCircle2,
  User,
  Briefcase,
  Shield,
  Users,
  CalendarDays,
  Timer,
  TrendingUp,
  Loader2,
  AlertCircle,
} from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { cn, formatDate, getInitials } from "@/lib/utils";
import * as employeesApi from "@/api/employees";

// ── Constants ──────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { label: string; className: string }> = {
  active: { label: "Active", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  notice_period: { label: "Notice Period", className: "bg-amber-50 text-amber-700 border-amber-200" },
  relieved: { label: "Relieved", className: "bg-slate-50 text-slate-600 border-slate-200" },
  absconding: { label: "Absconding", className: "bg-red-50 text-red-600 border-red-200" },
};

const ATTENDANCE_STATUS_COLORS: Record<string, string> = {
  present: "bg-emerald-500",
  work_from_home: "bg-emerald-400",
  on_duty: "bg-emerald-400",
  absent: "bg-red-500",
  half_day: "bg-amber-500",
  weekend: "bg-slate-200",
  holiday: "bg-blue-200",
  on_leave: "bg-purple-400",
};

const LEAVE_STATUS_STYLES: Record<string, { label: string; className: string }> = {
  pending: { label: "Pending", className: "bg-amber-50 text-amber-700 border-amber-200" },
  approved: { label: "Approved", className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  rejected: { label: "Rejected", className: "bg-red-50 text-red-600 border-red-200" },
  cancelled: { label: "Cancelled", className: "bg-slate-50 text-slate-500 border-slate-200" },
  revoked: { label: "Revoked", className: "bg-slate-50 text-slate-500 border-slate-200" },
};

// ── Main Component ─────────────────────────────────────────────────

export function EmployeeProfilePage() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();

  const profileQuery = useQuery({
    queryKey: ["employee-profile", employeeId],
    queryFn: () => employeesApi.getEmployeeProfile(employeeId!),
    enabled: !!employeeId,
    staleTime: 2 * 60 * 1000,
  });

  if (profileQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-32">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (profileQuery.isError || !profileQuery.data) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <AlertCircle className="h-10 w-10 text-red-400" />
        <h3 className="mt-3 text-lg font-medium">Failed to load profile</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          This employee may not exist or you don't have permission.
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => navigate("/employees")}>
          Back to Directory
        </Button>
      </div>
    );
  }

  const { employee, attendance_summary, recent_attendance, month_attendance, leave_balances, recent_leaves, team_members } =
    profileQuery.data.data;

  const displayName = employee.display_name || `${employee.first_name} ${employee.last_name}`;
  const empStatus = STATUS_STYLES[employee.employment_status] ?? STATUS_STYLES.active;

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button variant="ghost" size="sm" className="gap-1.5 -ml-2" onClick={() => navigate("/employees")}>
        <ArrowLeft className="h-4 w-4" />
        Employee Directory
      </Button>

      {/* ── Profile Header ──────────────────────────────────────── */}
      <Card className="py-0">
        <CardContent className="p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
            {/* Avatar */}
            <Avatar className="h-20 w-20 shrink-0 text-xl">
              {employee.profile_photo_url ? (
                <AvatarImage src={employee.profile_photo_url} alt={displayName} />
              ) : null}
              <AvatarFallback className="text-xl font-semibold">
                {getInitials(displayName)}
              </AvatarFallback>
            </Avatar>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold text-foreground">{displayName}</h1>
                <Badge variant="outline" className={cn("text-xs border", empStatus.className)}>
                  {empStatus.label}
                </Badge>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {employee.designation || employee.job_title || "—"}
              </p>

              <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
                <span className="flex items-center gap-1.5">
                  <Briefcase className="h-3.5 w-3.5" />
                  {employee.employee_code}
                </span>
                {employee.department && (
                  <span className="flex items-center gap-1.5">
                    <Building2 className="h-3.5 w-3.5" />
                    {employee.department.name}
                  </span>
                )}
                {employee.location && (
                  <span className="flex items-center gap-1.5">
                    <MapPin className="h-3.5 w-3.5" />
                    {employee.location.name}
                  </span>
                )}
                <a href={`mailto:${employee.email}`} className="flex items-center gap-1.5 hover:text-primary transition-colors">
                  <Mail className="h-3.5 w-3.5" />
                  {employee.email}
                </a>
                {employee.phone && (
                  <span className="flex items-center gap-1.5">
                    <Phone className="h-3.5 w-3.5" />
                    {employee.phone}
                  </span>
                )}
              </div>
            </div>

            {/* Quick Stats */}
            <div className="flex gap-3 sm:gap-4 shrink-0">
              <QuickStat
                icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" />}
                label="Present"
                value={attendance_summary.present_days}
              />
              <QuickStat
                icon={<AlertTriangle className="h-4 w-4 text-amber-600" />}
                label="Late"
                value={attendance_summary.late_count}
              />
              <QuickStat
                icon={<Users className="h-4 w-4 text-blue-600" />}
                label="Team"
                value={employee.direct_reports_count}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Tabbed Content ──────────────────────────────────────── */}
      <Tabs defaultValue="overview">
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="attendance">Attendance</TabsTrigger>
          <TabsTrigger value="leaves">Leaves</TabsTrigger>
          {team_members.length > 0 && (
            <TabsTrigger value="team">Team</TabsTrigger>
          )}
        </TabsList>

        {/* ── Overview Tab ────────────────────────────────────── */}
        <TabsContent value="overview" className="mt-4">
          <OverviewTab employee={employee} attendanceSummary={attendance_summary} />
        </TabsContent>

        {/* ── Attendance Tab ──────────────────────────────────── */}
        <TabsContent value="attendance" className="mt-4">
          <AttendanceTab
            summary={attendance_summary}
            recentAttendance={recent_attendance}
            monthAttendance={month_attendance}
          />
        </TabsContent>

        {/* ── Leaves Tab ──────────────────────────────────────── */}
        <TabsContent value="leaves" className="mt-4">
          <LeavesTab balances={leave_balances} recentLeaves={recent_leaves} />
        </TabsContent>

        {/* ── Team Tab ────────────────────────────────────────── */}
        {team_members.length > 0 && (
          <TabsContent value="team" className="mt-4">
            <TeamTab members={team_members} />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

// ── Quick Stat ─────────────────────────────────────────────────────

function QuickStat({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-border bg-muted/30 px-4 py-3 min-w-[72px]">
      {icon}
      <span className="text-lg font-bold text-foreground">{value}</span>
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// Overview Tab
// ═════════════════════════════════════════════════════════════════════

function OverviewTab({
  employee,
  attendanceSummary,
}: {
  employee: employeesApi.EmployeeDetail;
  attendanceSummary: employeesApi.AttendanceSummary;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {/* Personal Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <User className="h-4 w-4 text-muted-foreground" />
            Personal Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
            <InfoItem label="Full Name" value={`${employee.first_name}${employee.middle_name ? ` ${employee.middle_name}` : ""} ${employee.last_name}`} />
            <InfoItem label="Email" value={employee.email} />
            <InfoItem label="Personal Email" value={employee.personal_email} />
            <InfoItem label="Phone" value={employee.phone} />
            <InfoItem label="Gender" value={employee.gender ? capitalize(employee.gender) : null} />
            <InfoItem label="Date of Birth" value={employee.date_of_birth ? formatDate(employee.date_of_birth) : null} />
            <InfoItem label="Blood Group" value={employee.blood_group} />
            <InfoItem label="Marital Status" value={employee.marital_status ? capitalize(employee.marital_status) : null} />
            <InfoItem label="Nationality" value={employee.nationality} />
          </dl>
        </CardContent>
      </Card>

      {/* Employment Information */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Briefcase className="h-4 w-4 text-muted-foreground" />
            Employment Information
          </CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
            <InfoItem label="Employee Code" value={employee.employee_code} />
            <InfoItem label="Designation" value={employee.designation} />
            <InfoItem label="Job Title" value={employee.job_title} />
            <InfoItem label="Department" value={employee.department?.name} />
            <InfoItem label="Location" value={employee.location?.name} />
            <InfoItem label="Date of Joining" value={employee.date_of_joining ? formatDate(employee.date_of_joining) : null} />
            <InfoItem label="Reporting Manager" value={employee.reporting_manager?.display_name} />
            <InfoItem label="Employment Status" value={capitalize(employee.employment_status.replace(/_/g, " "))} />
            <InfoItem label="Notice Period" value={`${employee.notice_period_days} days`} />
            {employee.date_of_confirmation && (
              <InfoItem label="Confirmation Date" value={formatDate(employee.date_of_confirmation)} />
            )}
          </dl>
        </CardContent>
      </Card>

      {/* Address */}
      {(employee.current_address || employee.permanent_address) && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              Address
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-4 sm:grid-cols-2">
              {employee.current_address && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Current</p>
                  <AddressBlock address={employee.current_address} />
                </div>
              )}
              {employee.permanent_address && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">Permanent</p>
                  <AddressBlock address={employee.permanent_address} />
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Emergency Contact */}
      {employee.emergency_contact && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-4 w-4 text-muted-foreground" />
              Emergency Contact
            </CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-4 text-sm">
              <InfoItem label="Name" value={employee.emergency_contact.name} />
              <InfoItem label="Relationship" value={employee.emergency_contact.relationship} />
              <InfoItem label="Phone" value={employee.emergency_contact.phone} />
              <InfoItem label="Email" value={employee.emergency_contact.email} />
            </dl>
          </CardContent>
        </Card>
      )}

      {/* This Month at a Glance */}
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
            This Month at a Glance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              label="Present Days"
              value={attendanceSummary.present_days}
              total={attendanceSummary.total_working_days}
              icon={<CheckCircle2 className="h-5 w-5 text-emerald-500" />}
              color="emerald"
            />
            <StatCard
              label="Half Days"
              value={attendanceSummary.half_days}
              icon={<CalendarDays className="h-5 w-5 text-amber-500" />}
              color="amber"
            />
            <StatCard
              label="Late Arrivals"
              value={attendanceSummary.late_count}
              icon={<Timer className="h-5 w-5 text-red-500" />}
              color="red"
            />
            <StatCard
              label="Avg Check-in"
              value={attendanceSummary.avg_check_in || "—"}
              icon={<Clock className="h-5 w-5 text-blue-500" />}
              color="blue"
              isText
            />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// Attendance Tab
// ═════════════════════════════════════════════════════════════════════

function AttendanceTab({
  summary,
  recentAttendance,
  monthAttendance,
}: {
  summary: employeesApi.AttendanceSummary;
  recentAttendance: employeesApi.AttendanceDayRecord[];
  monthAttendance: employeesApi.AttendanceDayRecord[];
}) {
  const calendarData = useMemo(() => buildCalendarData(monthAttendance), [monthAttendance]);

  return (
    <div className="space-y-4">
      {/* Monthly Stats */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <MiniStat label="Present" value={summary.present_days} className="text-emerald-600 bg-emerald-50" />
        <MiniStat label="Half Days" value={summary.half_days} className="text-amber-600 bg-amber-50" />
        <MiniStat label="Late" value={summary.late_count} className="text-red-600 bg-red-50" />
        <MiniStat label="Working Days" value={summary.total_working_days} className="text-slate-600 bg-slate-50" />
        <MiniStat label="Avg Check-in" value={summary.avg_check_in || "—"} className="text-blue-600 bg-blue-50" isText />
      </div>

      {/* Calendar Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Attendance Calendar — {new Date().toLocaleString("en-IN", { month: "long", year: "numeric" })}
          </CardTitle>
          <CardDescription>Daily attendance status for the current month</CardDescription>
        </CardHeader>
        <CardContent>
          <AttendanceCalendar data={calendarData} />
          {/* Legend */}
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <LegendItem color="bg-emerald-500" label="Present" />
            <LegendItem color="bg-red-500" label="Absent" />
            <LegendItem color="bg-amber-500" label="Half Day" />
            <LegendItem color="bg-purple-400" label="On Leave" />
            <LegendItem color="bg-blue-200" label="Holiday" />
            <LegendItem color="bg-slate-200" label="Weekend" />
          </div>
        </CardContent>
      </Card>

      {/* Recent 7 Days */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Attendance (Last 7 Days)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Date</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Status</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Clock In</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Clock Out</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Hours</th>
                </tr>
              </thead>
              <tbody>
                {recentAttendance.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      No attendance records found
                    </td>
                  </tr>
                ) : (
                  recentAttendance.map((record) => (
                    <tr key={record.date} className="border-b last:border-0 hover:bg-muted/30">
                      <td className="px-4 py-2.5 font-medium">{formatDate(record.date)}</td>
                      <td className="px-4 py-2.5">
                        <AttendanceStatusBadge status={record.status} />
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {record.first_clock_in ? formatTimeFromISO(record.first_clock_in) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {record.last_clock_out ? formatTimeFromISO(record.last_clock_out) : "—"}
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">
                        {record.total_work_minutes != null ? `${(record.total_work_minutes / 60).toFixed(1)}h` : "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Attendance Calendar Heatmap ────────────────────────────────────

interface CalendarDay {
  date: number;
  dayOfWeek: number;
  status: string | null;
  isToday: boolean;
  isFuture: boolean;
}

function buildCalendarData(monthRecords: employeesApi.AttendanceDayRecord[]): CalendarDay[] {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();

  const statusMap = new Map(monthRecords.map((r) => [r.date, r.status]));

  const days: CalendarDay[] = [];
  for (let d = 1; d <= daysInMonth; d++) {
    const dateObj = new Date(year, month, d);
    const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    days.push({
      date: d,
      dayOfWeek: dateObj.getDay(),
      status: statusMap.get(dateStr) ?? null,
      isToday: d === today.getDate(),
      isFuture: d > today.getDate(),
    });
  }
  return days;
}

function AttendanceCalendar({ data }: { data: CalendarDay[] }) {
  const weekDays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  return (
    <div>
      {/* Header */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {weekDays.map((day) => (
          <div key={day} className="text-center text-[10px] font-medium text-muted-foreground py-1">
            {day}
          </div>
        ))}
      </div>
      {/* Days */}
      <div className="grid grid-cols-7 gap-1">
        {/* Offset for first day */}
        {data.length > 0 &&
          Array.from({ length: data[0].dayOfWeek }).map((_, i) => (
            <div key={`empty-${i}`} />
          ))}
        {data.map((day) => {
          const colorClass = day.isFuture
            ? "bg-muted/30"
            : day.status
              ? ATTENDANCE_STATUS_COLORS[day.status] ?? "bg-slate-200"
              : "bg-muted/50";

          return (
            <div
              key={day.date}
              className={cn(
                "relative aspect-square rounded-md flex items-center justify-center text-xs font-medium transition-all",
                colorClass,
                day.isFuture && "text-muted-foreground/40",
                !day.isFuture && day.status && "text-white",
                !day.isFuture && !day.status && "text-muted-foreground",
                day.isToday && "ring-2 ring-primary ring-offset-1",
              )}
              title={day.status ? `${day.date}: ${capitalize(day.status.replace(/_/g, " "))}` : `${day.date}`}
            >
              {day.date}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// Leaves Tab
// ═════════════════════════════════════════════════════════════════════

function LeavesTab({
  balances,
  recentLeaves,
}: {
  balances: employeesApi.LeaveBalanceItem[];
  recentLeaves: employeesApi.RecentLeaveRequest[];
}) {
  return (
    <div className="space-y-4">
      {/* Leave Balances */}
      {balances.length > 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {balances.map((bal, idx) => (
            <LeaveBalanceCard key={bal.leave_type?.id ?? idx} balance={bal} />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center py-10">
            <CalendarDays className="h-8 w-8 text-muted-foreground/40" />
            <p className="mt-2 text-sm text-muted-foreground">No leave balances found for this year</p>
          </CardContent>
        </Card>
      )}

      {/* Recent Leave Requests */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent Leave Requests</CardTitle>
          <CardDescription>Last 5 leave requests</CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50">
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Type</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Dates</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Days</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Status</th>
                  <th className="hidden px-4 py-2.5 text-left font-medium text-muted-foreground sm:table-cell">Reason</th>
                </tr>
              </thead>
              <tbody>
                {recentLeaves.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      No leave requests found
                    </td>
                  </tr>
                ) : (
                  recentLeaves.map((lr) => {
                    const status = LEAVE_STATUS_STYLES[lr.status] ?? LEAVE_STATUS_STYLES.pending;
                    return (
                      <tr key={lr.id} className="border-b last:border-0 hover:bg-muted/30">
                        <td className="px-4 py-2.5">
                          <Badge variant="secondary" className="text-xs font-normal">
                            {lr.leave_type?.name ?? "—"}
                          </Badge>
                        </td>
                        <td className="px-4 py-2.5 whitespace-nowrap">
                          {formatDate(lr.start_date)}
                          {lr.start_date !== lr.end_date && ` → ${formatDate(lr.end_date)}`}
                        </td>
                        <td className="px-4 py-2.5 font-medium">{lr.total_days}</td>
                        <td className="px-4 py-2.5">
                          <Badge variant="outline" className={cn("text-[10px] border", status.className)}>
                            {status.label}
                          </Badge>
                        </td>
                        <td className="hidden px-4 py-2.5 text-muted-foreground sm:table-cell max-w-[200px] truncate">
                          {lr.reason || "—"}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Leave Balance Card ─────────────────────────────────────────────

function LeaveBalanceCard({ balance }: { balance: employeesApi.LeaveBalanceItem }) {
  const total = balance.opening_balance + balance.accrued + balance.carry_forwarded + balance.adjusted;
  const used = balance.used;
  const remaining = balance.current_balance;
  const usedPct = total > 0 ? Math.min(100, (used / total) * 100) : 0;

  return (
    <Card className="py-0">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-sm font-semibold text-foreground">
            {balance.leave_type?.name ?? "Unknown"}
          </h4>
          <Badge variant="outline" className="text-[10px]">
            {balance.leave_type?.code ?? "?"}
          </Badge>
        </div>

        {/* Progress bar */}
        <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-primary transition-all duration-500"
            style={{ width: `${usedPct}%` }}
          />
        </div>

        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-lg font-bold text-foreground">{total}</p>
            <p className="text-[10px] text-muted-foreground uppercase">Total</p>
          </div>
          <div>
            <p className="text-lg font-bold text-amber-600">{used}</p>
            <p className="text-[10px] text-muted-foreground uppercase">Used</p>
          </div>
          <div>
            <p className="text-lg font-bold text-emerald-600">{remaining}</p>
            <p className="text-[10px] text-muted-foreground uppercase">Left</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ═════════════════════════════════════════════════════════════════════
// Team Tab
// ═════════════════════════════════════════════════════════════════════

function TeamTab({ members }: { members: employeesApi.TeamMember[] }) {
  const navigate = useNavigate();

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Users className="h-4 w-4" />
        <span>{members.length} direct report{members.length !== 1 ? "s" : ""}</span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {members.map((member) => (
          <Card
            key={member.id}
            className="py-0 cursor-pointer transition-shadow hover:shadow-md"
            onClick={() => navigate(`/employees/${member.id}`)}
          >
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <Avatar className="h-10 w-10">
                  {member.profile_photo_url ? (
                    <AvatarImage src={member.profile_photo_url} alt={member.display_name} />
                  ) : null}
                  <AvatarFallback className="text-xs">
                    {getInitials(member.display_name)}
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{member.display_name}</p>
                  <p className="truncate text-xs text-muted-foreground">{member.designation || "—"}</p>
                  {member.department && (
                    <Badge variant="secondary" className="mt-1 text-[10px] font-normal">
                      {member.department}
                    </Badge>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════════════
// Shared Components
// ═════════════════════════════════════════════════════════════════════

function InfoItem({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{label}</dt>
      <dd className="mt-0.5 text-sm text-foreground">{value || "—"}</dd>
    </div>
  );
}

function AddressBlock({ address }: { address: Record<string, string> }) {
  const parts = [address.line1, address.line2, address.city, address.state, address.pincode, address.country].filter(Boolean);
  return <p className="text-sm text-foreground">{parts.join(", ") || "—"}</p>;
}

function StatCard({
  label,
  value,
  total,
  icon,
  color,
  isText = false,
}: {
  label: string;
  value: number | string;
  total?: number;
  icon: React.ReactNode;
  color: string;
  isText?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card p-4">
      <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", `bg-${color}-50`)}>
        {icon}
      </div>
      <div>
        <p className="text-xl font-bold text-foreground">
          {isText ? value : value}
          {total != null && !isText && (
            <span className="text-sm font-normal text-muted-foreground">/{total}</span>
          )}
        </p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  className,
  isText: _isText = false,
}: {
  label: string;
  value: number | string;
  className: string;
  isText?: boolean;
}) {
  return (
    <div className={cn("rounded-lg p-3 text-center", className)}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs mt-0.5 opacity-80">{label}</p>
    </div>
  );
}

function AttendanceStatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    present: "bg-emerald-50 text-emerald-700 border-emerald-200",
    absent: "bg-red-50 text-red-600 border-red-200",
    half_day: "bg-amber-50 text-amber-700 border-amber-200",
    weekend: "bg-slate-50 text-slate-500 border-slate-200",
    holiday: "bg-blue-50 text-blue-600 border-blue-200",
    on_leave: "bg-purple-50 text-purple-600 border-purple-200",
    work_from_home: "bg-teal-50 text-teal-700 border-teal-200",
    on_duty: "bg-cyan-50 text-cyan-700 border-cyan-200",
  };

  return (
    <Badge variant="outline" className={cn("text-[10px] border", colorMap[status] ?? "")}>
      {capitalize(status.replace(/_/g, " "))}
    </Badge>
  );
}

function LegendItem({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={cn("h-3 w-3 rounded-sm", color)} />
      <span>{label}</span>
    </div>
  );
}

// ── Helpers ────────────────────────────────────────────────────────

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatTimeFromISO(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("en-IN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
      timeZone: "Asia/Kolkata",
    });
  } catch {
    return "—";
  }
}
