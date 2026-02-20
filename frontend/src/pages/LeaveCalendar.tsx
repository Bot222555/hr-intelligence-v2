/**
 * LeaveCalendar — Team leave calendar showing availability at a glance.
 *
 * Features:
 *  • Monthly calendar grid with employee leave overlays
 *  • Color-coded by leave type (CL=violet, EL=blue, SL=green, etc.)
 *  • Employee sidebar showing who's on leave each day
 *  • Month navigation with today highlight
 *  • Approved (solid) vs pending (striped) visual distinction
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Users,
  Clock,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn, formatDate, getInitials } from "@/lib/utils";
import * as leaveApi from "@/api/leave";
import type { LeaveCalendarEntry } from "@/api/leave";

// ── Helpers ────────────────────────────────────────────────────────

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function toDateStr(y: number, m: number, d: number): string {
  return `${y}-${pad2(m + 1)}-${pad2(d)}`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const DAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const TYPE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  CL: { bg: "bg-violet-100", border: "border-violet-300", text: "text-violet-700" },
  EL: { bg: "bg-blue-100", border: "border-blue-300", text: "text-blue-700" },
  SL: { bg: "bg-emerald-100", border: "border-emerald-300", text: "text-emerald-700" },
  ML: { bg: "bg-pink-100", border: "border-pink-300", text: "text-pink-700" },
  PL: { bg: "bg-pink-100", border: "border-pink-300", text: "text-pink-700" },
  CO: { bg: "bg-amber-100", border: "border-amber-300", text: "text-amber-700" },
};

const DEFAULT_TYPE_COLOR = { bg: "bg-slate-100", border: "border-slate-300", text: "text-slate-700" };

interface DayInfo {
  date: number;
  dateStr: string;
  isToday: boolean;
  isWeekend: boolean;
  entries: LeaveCalendarEntry[];
}

// ── Component ──────────────────────────────────────────────────────

export function LeaveCalendar() {
  const today = new Date();
  const [calYear, setCalYear] = useState(today.getFullYear());
  const [calMonth, setCalMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // ── Data fetching ────────────────────────────────────────────────

  const { data: calendarData, isLoading } = useQuery({
    queryKey: ["leaveCalendar", calYear, calMonth + 1],
    queryFn: () =>
      leaveApi.getLeaveCalendar({ month: calMonth + 1, year: calYear }),
  });

  // ── Build calendar grid ──────────────────────────────────────────

  const calendarDays = useMemo(() => {
    const firstDay = new Date(calYear, calMonth, 1);
    const lastDay = new Date(calYear, calMonth + 1, 0);
    const startOffset = firstDay.getDay();
    const totalDays = lastDay.getDate();

    const entries = calendarData?.entries || [];

    // Build a map: dateStr → entries on that date
    const entryMap = new Map<string, LeaveCalendarEntry[]>();
    for (const entry of entries) {
      const start = new Date(entry.start_date);
      const end = new Date(entry.end_date);
      // Clamp to month bounds
      const loopStart = start < firstDay ? firstDay : start;
      const loopEnd = end > lastDay ? lastDay : end;

      for (let dt = new Date(loopStart); dt <= loopEnd; dt.setDate(dt.getDate() + 1)) {
        const ds = toDateStr(dt.getFullYear(), dt.getMonth(), dt.getDate());
        if (!entryMap.has(ds)) entryMap.set(ds, []);
        entryMap.get(ds)!.push(entry);
      }
    }

    const days: (DayInfo | null)[] = [];

    // Leading blanks
    for (let i = 0; i < startOffset; i++) {
      days.push(null);
    }

    const todayDate = today.getDate();
    const todayMonth = today.getMonth();
    const todayYear = today.getFullYear();

    for (let d = 1; d <= totalDays; d++) {
      const dt = new Date(calYear, calMonth, d);
      const dateStr = toDateStr(calYear, calMonth, d);
      const dayOfWeek = dt.getDay();
      days.push({
        date: d,
        dateStr,
        isToday: d === todayDate && calMonth === todayMonth && calYear === todayYear,
        isWeekend: dayOfWeek === 0 || dayOfWeek === 6,
        entries: entryMap.get(dateStr) || [],
      });
    }

    return days;
  }, [calYear, calMonth, calendarData, today]);

  // ── Selected date details ────────────────────────────────────────

  const selectedDayInfo = useMemo(() => {
    if (!selectedDate) return null;
    return calendarDays.find(
      (d): d is DayInfo => d !== null && d.dateStr === selectedDate,
    );
  }, [selectedDate, calendarDays]);

  // ── Navigation ───────────────────────────────────────────────────

  const goPrevMonth = () => {
    setSelectedDate(null);
    if (calMonth === 0) {
      setCalYear((y) => y - 1);
      setCalMonth(11);
    } else {
      setCalMonth((m) => m - 1);
    }
  };

  const goNextMonth = () => {
    setSelectedDate(null);
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
    setSelectedDate(null);
  };

  // ── Stats ────────────────────────────────────────────────────────

  const stats = useMemo(() => {
    const entries = calendarData?.entries || [];
    const uniqueEmployees = new Set(entries.map((e) => e.employee.id));
    const pending = entries.filter((e) => e.status === "pending").length;
    const approved = entries.filter((e) => e.status === "approved").length;
    return { total: entries.length, unique: uniqueEmployees.size, pending, approved };
  }, [calendarData]);

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Leave Calendar</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Team availability overview — see who's on leave at a glance
        </p>
      </div>

      {/* Stats row */}
      <div className="grid gap-3 sm:grid-cols-4">
        <MiniStat
          icon={<CalendarDays className="h-4 w-4 text-primary" />}
          label="Total Leaves"
          value={stats.total}
        />
        <MiniStat
          icon={<Users className="h-4 w-4 text-blue-500" />}
          label="Employees"
          value={stats.unique}
        />
        <MiniStat
          icon={<CheckCircle2 className="h-4 w-4 text-emerald-500" />}
          label="Approved"
          value={stats.approved}
        />
        <MiniStat
          icon={<Clock className="h-4 w-4 text-amber-500" />}
          label="Pending"
          value={stats.pending}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        {/* Calendar grid */}
        <Card>
          <CardHeader className="flex-row items-center justify-between pb-2">
            <CardTitle className="flex items-center gap-2">
              <CalendarDays className="h-5 w-5 text-primary" />
              Team Calendar
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
            {isLoading ? (
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
                  if (day === null) {
                    return <div key={`blank-${i}`} className="aspect-square" />;
                  }

                  const hasLeaves = day.entries.length > 0;
                  const isSelected = selectedDate === day.dateStr;

                  // Count unique employees on leave
                  const uniqueEmpIds = new Set(day.entries.map((e) => e.employee.id));
                  const leaveCount = uniqueEmpIds.size;

                  return (
                    <button
                      key={day.dateStr}
                      onClick={() =>
                        setSelectedDate(
                          isSelected ? null : day.dateStr,
                        )
                      }
                      className={cn(
                        "relative flex aspect-square flex-col items-center justify-center rounded-lg border text-sm transition-all",
                        day.isToday && "ring-2 ring-primary ring-offset-1",
                        day.isWeekend && !hasLeaves && "bg-slate-50 border-slate-100 text-slate-400",
                        !day.isWeekend && !hasLeaves && "border-transparent hover:bg-muted/50",
                        hasLeaves && "border-primary/20 bg-primary/5 hover:bg-primary/10 cursor-pointer",
                        isSelected && "ring-2 ring-primary bg-primary/10",
                      )}
                    >
                      <span
                        className={cn(
                          "font-medium",
                          day.isToday && "font-bold text-primary",
                          day.isWeekend && !hasLeaves && "text-slate-400",
                        )}
                      >
                        {day.date}
                      </span>
                      {hasLeaves && (
                        <div className="flex items-center gap-0.5 mt-0.5">
                          {leaveCount <= 3 ? (
                            // Show dots for each person
                            Array.from(uniqueEmpIds)
                              .slice(0, 3)
                              .map((_, idx) => {
                                const entry = day.entries[idx];
                                const code = entry?.leave_type?.code || "??";
                                const color = TYPE_COLORS[code] || DEFAULT_TYPE_COLOR;
                                return (
                                  <span
                                    key={idx}
                                    className={cn("h-1.5 w-1.5 rounded-full", color.bg, color.border, "border")}
                                  />
                                );
                              })
                          ) : (
                            <span className="text-[10px] font-semibold text-primary">
                              {leaveCount}
                            </span>
                          )}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            {/* Legend */}
            <div className="mt-4 flex flex-wrap items-center gap-4 border-t pt-4 text-xs">
              <span className="font-medium text-muted-foreground">Legend:</span>
              {Object.entries(TYPE_COLORS).map(([code, colors]) => (
                <span key={code} className="flex items-center gap-1.5">
                  <span
                    className={cn(
                      "h-2.5 w-2.5 rounded-full border",
                      colors.bg,
                      colors.border,
                    )}
                  />
                  <span className="text-muted-foreground">{code}</span>
                </span>
              ))}
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full border bg-slate-100 border-slate-300" />
                <span className="text-muted-foreground">Other</span>
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Sidebar: selected day details */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">
                {selectedDayInfo
                  ? formatDate(selectedDayInfo.dateStr)
                  : "Select a day"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!selectedDayInfo ? (
                <p className="text-sm text-muted-foreground py-4 text-center">
                  Click on a day to see who's on leave
                </p>
              ) : selectedDayInfo.entries.length === 0 ? (
                <div className="flex flex-col items-center py-6">
                  <CheckCircle2 className="h-8 w-8 text-emerald-400" />
                  <p className="mt-2 text-sm font-medium text-emerald-700">
                    Full Team Available
                  </p>
                  <p className="text-xs text-muted-foreground">
                    No one is on leave this day
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {/* De-duplicate by employee */}
                  {dedupeByEmployee(selectedDayInfo.entries).map((entry) => {
                    const code = entry.leave_type?.code || "??";
                    const colors = TYPE_COLORS[code] || DEFAULT_TYPE_COLOR;
                    const emp = entry.employee;

                    return (
                      <div
                        key={`${entry.employee.id}-${entry.start_date}`}
                        className={cn(
                          "flex items-center gap-3 rounded-lg border p-3",
                          colors.border,
                          entry.status === "pending" ? "bg-amber-50/50" : colors.bg + "/30",
                        )}
                      >
                        <Avatar size="sm">
                          {emp.profile_photo_url && (
                            <AvatarImage
                              src={emp.profile_photo_url}
                              alt={emp.display_name || ""}
                            />
                          )}
                          <AvatarFallback className="text-[10px]">
                            {getInitials(emp.display_name || "??")}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-foreground truncate">
                            {emp.display_name || emp.employee_code}
                          </p>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <Badge
                              className={cn(
                                "text-[10px] px-1.5 py-0 border",
                                colors.bg,
                                colors.border,
                                colors.text,
                              )}
                            >
                              {entry.leave_type?.name || code}
                            </Badge>
                            {entry.status === "pending" && (
                              <Badge className="text-[10px] px-1.5 py-0 border bg-amber-50 border-amber-200 text-amber-700">
                                <Clock className="h-2.5 w-2.5 mr-0.5" />
                                Pending
                              </Badge>
                            )}
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-xs font-medium tabular-nums text-foreground">
                            {Number(entry.total_days)}d
                          </p>
                          {/* Show half-day info */}
                          {selectedDayInfo &&
                            entry.day_details[selectedDayInfo.dateStr] &&
                            entry.day_details[selectedDayInfo.dateStr] !== "full_day" && (
                              <p className="text-[10px] text-muted-foreground">
                                {entry.day_details[selectedDayInfo.dateStr] === "first_half"
                                  ? "1st half"
                                  : "2nd half"}
                              </p>
                            )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Upcoming leaves (next 7 days) */}
          <UpcomingLeaves entries={calendarData?.entries || []} calYear={calYear} calMonth={calMonth} />
        </div>
      </div>
    </div>
  );
}

// ── Upcoming Leaves Card ───────────────────────────────────────────

function UpcomingLeaves({
  entries,
}: {
  entries: LeaveCalendarEntry[];
  calYear: number;
  calMonth: number;
}) {
  const upcoming = useMemo(() => {
    const today = new Date();
    const weekOut = new Date(today);
    weekOut.setDate(weekOut.getDate() + 7);

    return entries
      .filter((e) => {
        const start = new Date(e.start_date);
        return start >= today && start <= weekOut && e.status === "approved";
      })
      .sort((a, b) => new Date(a.start_date).getTime() - new Date(b.start_date).getTime())
      .slice(0, 5);
  }, [entries]);

  if (upcoming.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <AlertCircle className="h-4 w-4 text-amber-500" />
          Upcoming (7 days)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {upcoming.map((entry) => (
            <div
              key={`${entry.employee.id}-${entry.start_date}`}
              className="flex items-center justify-between text-sm"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Avatar size="sm">
                  {entry.employee.profile_photo_url && (
                    <AvatarImage
                      src={entry.employee.profile_photo_url}
                      alt={entry.employee.display_name || ""}
                    />
                  )}
                  <AvatarFallback className="text-[10px]">
                    {getInitials(entry.employee.display_name || "??")}
                  </AvatarFallback>
                </Avatar>
                <span className="truncate text-foreground">
                  {entry.employee.display_name?.split(" ")[0] || entry.employee.employee_code}
                </span>
              </div>
              <span className="text-xs text-muted-foreground whitespace-nowrap ml-2">
                {formatDate(entry.start_date)}
                {entry.start_date !== entry.end_date && (
                  <>–{formatDate(entry.end_date)}</>
                )}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Mini Stat ──────────────────────────────────────────────────────

function MiniStat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <Card className="py-3">
      <CardContent className="flex items-center gap-3 px-4 py-0">
        {icon}
        <div>
          <p className="text-xl font-bold tabular-nums text-foreground">{value}</p>
          <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Utility ────────────────────────────────────────────────────────

function dedupeByEmployee(entries: LeaveCalendarEntry[]): LeaveCalendarEntry[] {
  const seen = new Set<string>();
  return entries.filter((e) => {
    const key = `${e.employee.id}-${e.start_date}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
