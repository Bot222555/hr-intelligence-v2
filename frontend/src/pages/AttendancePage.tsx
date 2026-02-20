/**
 * AttendancePage — Employee self-service attendance view.
 *
 * Features:
 *  • Clock in / out button with live running timer
 *  • Today's attendance status card
 *  • Monthly calendar view with color-coded days
 *    (present = green, absent = red, leave = blue, holiday = gray,
 *     half_day = amber, weekend = slate, WFH = teal)
 *  • Summary stats for the selected month
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Clock,
  LogIn,
  LogOut,
  ChevronLeft,
  ChevronRight,
  Timer,
  CalendarDays,
  TrendingUp,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Coffee,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatTime } from "@/lib/utils";
import * as attendanceApi from "@/api/attendance";
import type {
  AttendanceRecord,
  AttendanceStatus,
  Holiday,
} from "@/api/attendance";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  AttendanceStatus,
  { label: string; dot: string; bg: string; text: string }
> = {
  present: {
    label: "Present",
    dot: "bg-emerald-500",
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
  },
  absent: {
    label: "Absent",
    dot: "bg-red-500",
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
  },
  half_day: {
    label: "Half Day",
    dot: "bg-amber-500",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
  },
  weekend: {
    label: "Weekend",
    dot: "bg-slate-400",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
  },
  holiday: {
    label: "Holiday",
    dot: "bg-slate-500",
    bg: "bg-slate-100 border-slate-300",
    text: "text-slate-700",
  },
  on_leave: {
    label: "On Leave",
    dot: "bg-blue-500",
    bg: "bg-blue-50 border-blue-200",
    text: "text-blue-700",
  },
  work_from_home: {
    label: "WFH",
    dot: "bg-teal-500",
    bg: "bg-teal-50 border-teal-200",
    text: "text-teal-700",
  },
  on_duty: {
    label: "On Duty",
    dot: "bg-indigo-500",
    bg: "bg-indigo-50 border-indigo-200",
    text: "text-indigo-700",
  },
};

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${pad2(h)}:${pad2(m)}:${pad2(s)}`;
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function getMonthRange(year: number, month: number) {
  const from = new Date(year, month, 1);
  const to = new Date(year, month + 1, 0);
  return { from: toDateStr(from), to: toDateStr(to) };
}

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

// ── Component ──────────────────────────────────────────────────────

export function AttendancePage() {
  const queryClient = useQueryClient();
  const today = new Date();
  const [calYear, setCalYear] = useState(today.getFullYear());
  const [calMonth, setCalMonth] = useState(today.getMonth());

  // ── Clock state ──────────────────────────────────────────────────

  const [clockedIn, setClockedIn] = useState(false);
  const [clockInTime, setClockInTime] = useState<Date | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [clockError, setClockError] = useState<string | null>(null);

  // Live timer
  useEffect(() => {
    if (!clockedIn || !clockInTime) return;
    const tick = () =>
      setElapsed(Math.floor((Date.now() - clockInTime.getTime()) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [clockedIn, clockInTime]);

  // ── Data fetching ────────────────────────────────────────────────

  const { from, to } = getMonthRange(calYear, calMonth);

  const {
    data: attendanceData,
    isLoading: isLoadingAttendance,
  } = useQuery({
    queryKey: ["myAttendance", from, to],
    queryFn: () => attendanceApi.getMyAttendance(from, to, 1, 100),
  });

  const { data: holidays } = useQuery({
    queryKey: ["holidays", calYear],
    queryFn: () => attendanceApi.getHolidays({ year: calYear }),
  });

  // Derive today's record to initialize clock state
  const todayStr = toDateStr(today);
  const todayRecord = (attendanceData?.data ?? []).find((r) => r.date === todayStr);

  useEffect(() => {
    if (todayRecord && todayRecord.first_clock_in && !todayRecord.last_clock_out) {
      setClockedIn(true);
      setClockInTime(new Date(todayRecord.first_clock_in));
    } else if (todayRecord && todayRecord.last_clock_out) {
      setClockedIn(false);
      setClockInTime(todayRecord.first_clock_in ? new Date(todayRecord.first_clock_in) : null);
    }
  }, [todayRecord]);

  // ── Mutations ────────────────────────────────────────────────────

  const clockInMut = useMutation({
    mutationFn: () => attendanceApi.clockIn("web"),
    onSuccess: (resp) => {
      setClockedIn(true);
      setClockInTime(new Date(resp.timestamp));
      setClockError(null);
      queryClient.invalidateQueries({ queryKey: ["myAttendance"] });
    },
    onError: (err: any) => {
      setClockError(
        err?.response?.data?.detail || err?.message || "Failed to clock in",
      );
    },
  });

  const clockOutMut = useMutation({
    mutationFn: () => attendanceApi.clockOut("web"),
    onSuccess: () => {
      setClockedIn(false);
      setClockError(null);
      queryClient.invalidateQueries({ queryKey: ["myAttendance"] });
    },
    onError: (err: any) => {
      setClockError(
        err?.response?.data?.detail || err?.message || "Failed to clock out",
      );
    },
  });

  const handleClock = useCallback(() => {
    setClockError(null);
    if (clockedIn) {
      clockOutMut.mutate();
    } else {
      clockInMut.mutate();
    }
  }, [clockedIn, clockInMut, clockOutMut]);

  // ── Calendar data ────────────────────────────────────────────────

  const recordMap = useMemo(() => {
    const map = new Map<string, AttendanceRecord>();
    (attendanceData?.data ?? []).forEach((r) => map.set(r.date, r));
    return map;
  }, [attendanceData]);

  const holidayMap = useMemo(() => {
    const map = new Map<string, Holiday>();
    (holidays ?? []).forEach((h) => map.set(h.date, h));
    return map;
  }, [holidays]);

  // Build calendar grid
  const calendarDays = useMemo(() => {
    const firstDay = new Date(calYear, calMonth, 1);
    const lastDay = new Date(calYear, calMonth + 1, 0);
    const startOffset = firstDay.getDay();
    const totalDays = lastDay.getDate();

    const days: Array<{
      date: number | null;
      dateStr: string;
      status: AttendanceStatus | "weekend" | "future" | "no-data";
      holiday?: Holiday;
      record?: AttendanceRecord;
      isToday: boolean;
    }> = [];

    // Leading blanks
    for (let i = 0; i < startOffset; i++) {
      days.push({ date: null, dateStr: "", status: "no-data", isToday: false });
    }

    const todayDate = today.getDate();
    const todayMonth = today.getMonth();
    const todayYear = today.getFullYear();

    for (let d = 1; d <= totalDays; d++) {
      const dt = new Date(calYear, calMonth, d);
      const dateStr = toDateStr(dt);
      const isToday =
        d === todayDate && calMonth === todayMonth && calYear === todayYear;
      const dayOfWeek = dt.getDay();
      const isWeekend = dayOfWeek === 0 || dayOfWeek === 6;
      const holiday = holidayMap.get(dateStr);
      const record = recordMap.get(dateStr);
      const isFuture = dt > today;

      let status: AttendanceStatus | "weekend" | "future" | "no-data";
      if (isFuture) {
        status = holiday ? "holiday" : "future";
      } else if (holiday) {
        status = "holiday";
      } else if (record) {
        status = record.status;
      } else if (isWeekend) {
        status = "weekend";
      } else if (!isFuture) {
        status = "absent";
      } else {
        status = "no-data";
      }

      days.push({ date: d, dateStr, status, holiday, record, isToday });
    }

    return days;
  }, [calYear, calMonth, recordMap, holidayMap, today]);

  // ── Navigation ───────────────────────────────────────────────────

  const goPrevMonth = () => {
    if (calMonth === 0) {
      setCalYear((y) => y - 1);
      setCalMonth(11);
    } else {
      setCalMonth((m) => m - 1);
    }
  };

  const goNextMonth = () => {
    if (calMonth === 11) {
      setCalYear((y) => y + 1);
      setCalMonth(0);
    } else {
      setCalMonth((m) => m + 1);
    }
  };

  const goToday = () => {
    setCalYear(today.getFullYear());
    setCalMonth(today.getMonth());
  };

  // ── Summary stats ────────────────────────────────────────────────

  const summary = attendanceData?.summary;

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Attendance</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Track your daily attendance and view your monthly calendar
        </p>
      </div>

      {/* Top row: Clock card + Today's status */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Clock In/Out Card */}
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div
              className={cn(
                "flex flex-col items-center gap-4 px-6 py-8 transition-colors",
                clockedIn
                  ? "bg-gradient-to-br from-emerald-50 to-teal-50"
                  : "bg-gradient-to-br from-slate-50 to-gray-50",
              )}
            >
              {/* Timer display */}
              <div className="flex items-center gap-2 text-muted-foreground">
                <Timer className="h-4 w-4" />
                <span className="text-xs font-medium uppercase tracking-wider">
                  {clockedIn ? "Working Time" : "Not Clocked In"}
                </span>
              </div>

              <div
                className={cn(
                  "font-mono text-5xl font-bold tabular-nums tracking-tight",
                  clockedIn ? "text-emerald-700" : "text-slate-400",
                )}
              >
                {clockedIn ? formatDuration(elapsed) : "00:00:00"}
              </div>

              {clockInTime && (
                <p className="text-sm text-muted-foreground">
                  Clocked in at{" "}
                  <span className="font-medium text-foreground">
                    {formatTime(clockInTime)}
                  </span>
                  {todayRecord?.last_clock_out && (
                    <>
                      {" · "}Out at{" "}
                      <span className="font-medium text-foreground">
                        {formatTime(todayRecord.last_clock_out)}
                      </span>
                    </>
                  )}
                </p>
              )}

              {/* Clock button */}
              <Button
                size="lg"
                onClick={handleClock}
                disabled={clockInMut.isPending || clockOutMut.isPending}
                className={cn(
                  "mt-2 min-w-[200px] gap-2 text-base font-semibold shadow-md transition-all",
                  clockedIn
                    ? "bg-red-500 hover:bg-red-600 text-white"
                    : "bg-emerald-600 hover:bg-emerald-700 text-white",
                )}
              >
                {clockedIn ? (
                  <>
                    <LogOut className="h-5 w-5" />
                    {clockOutMut.isPending ? "Clocking Out…" : "Clock Out"}
                  </>
                ) : (
                  <>
                    <LogIn className="h-5 w-5" />
                    {clockInMut.isPending ? "Clocking In…" : "Clock In"}
                  </>
                )}
              </Button>

              {clockError && (
                <p className="mt-1 flex items-center gap-1.5 text-sm text-red-600">
                  <AlertCircle className="h-4 w-4" />
                  {clockError}
                </p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Today's Status + Monthly Summary */}
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Today Status */}
          <Card>
            <CardContent className="flex flex-col items-center justify-center gap-3 py-6">
              <div className="rounded-full bg-primary/10 p-3">
                <Clock className="h-6 w-6 text-primary" />
              </div>
              <div className="text-center">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Today's Status
                </p>
                {todayRecord ? (
                  <Badge
                    className={cn(
                      "mt-2 border text-sm",
                      STATUS_CONFIG[todayRecord.status]?.bg,
                      STATUS_CONFIG[todayRecord.status]?.text,
                    )}
                  >
                    {STATUS_CONFIG[todayRecord.status]?.label || todayRecord.status}
                  </Badge>
                ) : (
                  <Badge className="mt-2 border bg-slate-50 border-slate-200 text-slate-600 text-sm">
                    Not Clocked In
                  </Badge>
                )}
              </div>
              {todayRecord?.total_hours != null && (
                <p className="text-sm text-muted-foreground">
                  {todayRecord.total_hours.toFixed(1)}h total
                  {todayRecord.effective_hours != null &&
                    ` · ${todayRecord.effective_hours.toFixed(1)}h effective`}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Monthly Summary Stats */}
          <div className="grid grid-cols-2 gap-3">
            <MiniStat
              icon={<CheckCircle2 className="h-4 w-4 text-emerald-600" />}
              label="Present"
              value={summary?.present ?? 0}
              color="text-emerald-700"
            />
            <MiniStat
              icon={<XCircle className="h-4 w-4 text-red-500" />}
              label="Absent"
              value={summary?.absent ?? 0}
              color="text-red-600"
            />
            <MiniStat
              icon={<Coffee className="h-4 w-4 text-amber-500" />}
              label="Half Day"
              value={summary?.half_day ?? 0}
              color="text-amber-600"
            />
            <MiniStat
              icon={<TrendingUp className="h-4 w-4 text-blue-500" />}
              label="Avg Hours"
              value={summary?.avg_hours ? `${summary.avg_hours.toFixed(1)}h` : "—"}
              color="text-blue-600"
            />
          </div>
        </div>
      </div>

      {/* Calendar Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs">
        <span className="font-medium text-muted-foreground">Legend:</span>
        {(
          [
            ["present", "Present"],
            ["absent", "Absent"],
            ["on_leave", "Leave"],
            ["holiday", "Holiday"],
            ["half_day", "Half Day"],
            ["weekend", "Weekend"],
            ["work_from_home", "WFH"],
          ] as [AttendanceStatus, string][]
        ).map(([key, label]) => (
          <span key={key} className="flex items-center gap-1.5">
            <span
              className={cn("h-2.5 w-2.5 rounded-full", STATUS_CONFIG[key]?.dot)}
            />
            <span className="text-muted-foreground">{label}</span>
          </span>
        ))}
      </div>

      {/* Monthly Calendar */}
      <Card>
        <CardHeader className="flex-row items-center justify-between pb-2">
          <CardTitle className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-primary" />
            Monthly Calendar
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon-sm" onClick={goPrevMonth}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <button
              onClick={goToday}
              className="min-w-[160px] rounded-md px-3 py-1 text-sm font-semibold text-foreground hover:bg-muted transition-colors"
            >
              {MONTH_NAMES[calMonth]} {calYear}
            </button>
            <Button variant="outline" size="icon-sm" onClick={goNextMonth}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoadingAttendance ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : (
            <div className="grid grid-cols-7 gap-1">
              {/* Day headers */}
              {DAY_LABELS.map((d) => (
                <div
                  key={d}
                  className="py-2 text-center text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  {d}
                </div>
              ))}

              {/* Calendar cells */}
              {calendarDays.map((day, i) => {
                if (day.date === null) {
                  return <div key={`blank-${i}`} className="aspect-square" />;
                }

                const cfg =
                  day.status === "future" || day.status === "no-data"
                    ? null
                    : STATUS_CONFIG[day.status as AttendanceStatus];

                return (
                  <div
                    key={day.dateStr}
                    className={cn(
                      "relative flex aspect-square flex-col items-center justify-center rounded-lg border text-sm transition-all",
                      day.isToday && "ring-2 ring-primary ring-offset-1",
                      cfg ? cfg.bg : "border-transparent",
                      day.status === "future" && "border-dashed border-slate-200 text-slate-300",
                      day.status === "no-data" && "text-slate-300",
                    )}
                    title={
                      day.holiday
                        ? `${day.holiday.name}`
                        : day.record
                          ? `${STATUS_CONFIG[day.record.status]?.label}${day.record.total_hours != null ? ` — ${day.record.total_hours.toFixed(1)}h` : ""}`
                          : undefined
                    }
                  >
                    <span
                      className={cn(
                        "font-medium",
                        cfg?.text,
                        day.isToday && "font-bold",
                      )}
                    >
                      {day.date}
                    </span>

                    {/* Holiday name or hours */}
                    {day.holiday && (
                      <span className="absolute bottom-0.5 text-[9px] leading-none text-slate-500 truncate max-w-full px-0.5">
                        {day.holiday.name.length > 6
                          ? day.holiday.name.slice(0, 6) + "…"
                          : day.holiday.name}
                      </span>
                    )}
                    {!day.holiday &&
                      day.record?.total_hours != null &&
                      day.record.total_hours > 0 && (
                        <span className="text-[10px] leading-none text-muted-foreground">
                          {day.record.total_hours.toFixed(1)}h
                        </span>
                      )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Mini Stat Card ─────────────────────────────────────────────────

function MiniStat({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  color: string;
}) {
  return (
    <Card className="py-3">
      <CardContent className="flex flex-col items-center gap-1 px-3 py-0">
        {icon}
        <span className={cn("text-xl font-bold tabular-nums", color)}>
          {value}
        </span>
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      </CardContent>
    </Card>
  );
}
