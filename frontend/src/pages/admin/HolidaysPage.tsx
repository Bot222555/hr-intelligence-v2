/**
 * Admin Holidays Page — Calendar view with color-coded holidays.
 * CRUD operations for company holidays.
 * Only visible to system_admin and hr_admin roles.
 */

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarHeart,
  Plus,
  Edit3,
  Trash2,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  Sparkles,
  Flag,
  Star,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import * as adminApi from "@/api/admin";
import type { Holiday } from "@/api/admin";

// ── Helpers ────────────────────────────────────────────────────────

const HOLIDAY_TYPE_CONFIG = {
  national: {
    label: "National",
    bg: "bg-red-50",
    border: "border-red-200",
    text: "text-red-700",
    dot: "bg-red-500",
    icon: Flag,
  },
  restricted: {
    label: "Restricted",
    bg: "bg-amber-50",
    border: "border-amber-200",
    text: "text-amber-700",
    dot: "bg-amber-500",
    icon: Star,
  },
  optional: {
    label: "Optional",
    bg: "bg-blue-50",
    border: "border-blue-200",
    text: "text-blue-700",
    dot: "bg-blue-500",
    icon: Sparkles,
  },
};

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}

function formatDate(d: string | Date): string {
  const date = typeof d === "string" ? new Date(d + "T00:00:00") : d;
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

// ── Holiday Form ───────────────────────────────────────────────────

function HolidayForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<Holiday>;
  onSave: (data: adminApi.HolidayCreate) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    name: initial?.name || "",
    date: initial?.date || "",
    type: (initial?.type || "national") as "national" | "restricted" | "optional",
  });

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Holiday Name</label>
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Republic Day"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Date</label>
          <input
            type="date"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Type</label>
          <select
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value as typeof form.type })}
          >
            <option value="national">National</option>
            <option value="restricted">Restricted</option>
            <option value="optional">Optional</option>
          </select>
        </div>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onSave(form)} disabled={!form.name || !form.date}>
          <Check className="mr-1 h-4 w-4" /> Save
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>
          <X className="mr-1 h-4 w-4" /> Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Calendar Grid ──────────────────────────────────────────────────

function CalendarMonth({
  year,
  month,
  holidays,
  onDayClick,
}: {
  year: number;
  month: number;
  holidays: Holiday[];
  onDayClick: (date: string) => void;
}) {
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const today = new Date();
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month;

  const holidayMap = useMemo(() => {
    const map: Record<number, Holiday> = {};
    for (const h of holidays) {
      const d = new Date(h.date + "T00:00:00");
      if (d.getFullYear() === year && d.getMonth() === month) {
        map[d.getDate()] = h;
      }
    }
    return map;
  }, [holidays, year, month]);

  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-foreground">{MONTHS[month]}</h3>
      <div className="grid grid-cols-7 gap-px rounded-lg border border-border bg-border overflow-hidden">
        {WEEKDAYS.map((d) => (
          <div
            key={d}
            className="bg-muted px-1 py-1 text-center text-[10px] font-medium text-muted-foreground"
          >
            {d}
          </div>
        ))}
        {cells.map((day, i) => {
          if (day === null) {
            return <div key={`empty-${i}`} className="bg-background p-1" />;
          }

          const holiday = holidayMap[day];
          const cfg = holiday ? HOLIDAY_TYPE_CONFIG[holiday.type] : null;
          const isToday = isCurrentMonth && day === today.getDate();
          const dateStr = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
          const isWeekend = new Date(year, month, day).getDay() === 0 || new Date(year, month, day).getDay() === 6;

          return (
            <div
              key={day}
              className={cn(
                "relative min-h-[32px] cursor-pointer bg-background p-1 text-center transition-colors hover:bg-muted/50",
                holiday && cfg && `${cfg.bg}`,
                isToday && "ring-1 ring-inset ring-primary"
              )}
              onClick={() => onDayClick(dateStr)}
              title={holiday ? `${holiday.name} (${holiday.type})` : undefined}
            >
              <span
                className={cn(
                  "text-xs",
                  holiday && cfg ? cfg.text + " font-semibold" : "",
                  isWeekend && !holiday ? "text-muted-foreground" : "",
                  isToday && "font-bold"
                )}
              >
                {day}
              </span>
              {holiday && cfg && (
                <div className={cn("mx-auto mt-0.5 h-1 w-1 rounded-full", cfg.dot)} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Main Holidays Page ─────────────────────────────────────────────

export function HolidaysPage() {
  const queryClient = useQueryClient();
  const [year, setYear] = useState(2026);
  const [showForm, setShowForm] = useState(false);
  const [editingHoliday, setEditingHoliday] = useState<Holiday | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const { data: holidays = [], isLoading } = useQuery({
    queryKey: ["admin", "holidays", year],
    queryFn: () => adminApi.getHolidays(year),
  });

  const createHoliday = useMutation({
    mutationFn: adminApi.createHoliday,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "holidays"] });
      setShowForm(false);
      setSelectedDate(null);
    },
  });

  const updateHoliday = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Holiday> }) =>
      adminApi.updateHoliday(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "holidays"] });
      setEditingHoliday(null);
    },
  });

  const deleteHoliday = useMutation({
    mutationFn: adminApi.deleteHoliday,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "holidays"] });
    },
  });

  const seedHolidays = useMutation({
    mutationFn: adminApi.seedHolidays2026,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "holidays"] });
    },
  });

  const handleDayClick = (dateStr: string) => {
    const existing = holidays.find((h) => h.date === dateStr);
    if (existing) {
      setEditingHoliday(existing);
      setShowForm(false);
    } else {
      setSelectedDate(dateStr);
      setShowForm(true);
      setEditingHoliday(null);
    }
  };

  // Stats
  const typeCounts = useMemo(() => {
    const counts = { national: 0, restricted: 0, optional: 0 };
    for (const h of holidays) {
      if (h.type in counts) counts[h.type as keyof typeof counts]++;
    }
    return counts;
  }, [holidays]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Holiday Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Manage company holidays for {year}.
          </p>
        </div>
        <div className="flex gap-2">
          {year === 2026 && holidays.length === 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => seedHolidays.mutate()}
              disabled={seedHolidays.isPending}
            >
              <Sparkles className="mr-1 h-4 w-4" />
              {seedHolidays.isPending ? "Seeding..." : "Seed 2026 Holidays"}
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => {
              setShowForm(true);
              setEditingHoliday(null);
              setSelectedDate(null);
            }}
          >
            <Plus className="mr-1 h-4 w-4" /> Add Holiday
          </Button>
        </div>
      </div>

      {/* Year Selector + Legend */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={() => setYear(year - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-lg font-bold">{year}</span>
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8"
            onClick={() => setYear(year + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex gap-4">
          {Object.entries(HOLIDAY_TYPE_CONFIG).map(([key, cfg]) => (
            <div key={key} className="flex items-center gap-1.5">
              <div className={cn("h-2.5 w-2.5 rounded-full", cfg.dot)} />
              <span className="text-xs text-muted-foreground">
                {cfg.label} ({typeCounts[key as keyof typeof typeCounts] || 0})
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Form */}
      {showForm && (
        <HolidayForm
          initial={selectedDate ? { date: selectedDate } : undefined}
          onSave={(data) => createHoliday.mutate(data)}
          onCancel={() => {
            setShowForm(false);
            setSelectedDate(null);
          }}
        />
      )}
      {editingHoliday && (
        <div className="space-y-3">
          <HolidayForm
            initial={editingHoliday}
            onSave={(data) =>
              updateHoliday.mutate({ id: editingHoliday.id, data })
            }
            onCancel={() => setEditingHoliday(null)}
          />
          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              if (confirm(`Delete "${editingHoliday.name}"?`)) {
                deleteHoliday.mutate(editingHoliday.id);
                setEditingHoliday(null);
              }
            }}
          >
            <Trash2 className="mr-1 h-4 w-4" /> Delete Holiday
          </Button>
        </div>
      )}

      {/* Calendar Grid */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">
          Loading holiday calendar...
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 12 }, (_, i) => (
            <CalendarMonth
              key={i}
              year={year}
              month={i}
              holidays={holidays}
              onDayClick={handleDayClick}
            />
          ))}
        </div>
      )}

      {/* Holiday List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CalendarHeart className="h-5 w-5 text-primary" />
            All Holidays ({holidays.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {holidays.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              No holidays configured for {year}.
              {year === 2026 && ' Click "Seed 2026 Holidays" to add Indian national holidays.'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th className="py-3 pr-4">Date</th>
                    <th className="py-3 pr-4">Holiday</th>
                    <th className="py-3 pr-4">Type</th>
                    <th className="py-3 pr-4">Day</th>
                    <th className="py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {holidays.map((h) => {
                    const cfg = HOLIDAY_TYPE_CONFIG[h.type] || HOLIDAY_TYPE_CONFIG.national;
                    const Icon = cfg.icon;
                    const date = new Date(h.date + "T00:00:00");
                    const dayName = date.toLocaleDateString("en-IN", { weekday: "long" });

                    return (
                      <tr key={h.id} className="group hover:bg-muted/30">
                        <td className="py-3 pr-4 font-medium">{formatDate(h.date)}</td>
                        <td className="py-3 pr-4">{h.name}</td>
                        <td className="py-3 pr-4">
                          <Badge variant="outline" className={cn("gap-1", cfg.bg, cfg.border, cfg.text)}>
                            <Icon className="h-3 w-3" />
                            {cfg.label}
                          </Badge>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">{dayName}</td>
                        <td className="py-3 text-right">
                          <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100">
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-7 w-7"
                              onClick={() => setEditingHoliday(h)}
                            >
                              <Edit3 className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              size="icon"
                              variant="ghost"
                              className="h-7 w-7 text-destructive"
                              onClick={() => {
                                if (confirm(`Delete "${h.name}"?`)) {
                                  deleteHoliday.mutate(h.id);
                                }
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
