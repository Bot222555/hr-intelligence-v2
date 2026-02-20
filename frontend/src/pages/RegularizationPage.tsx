/**
 * RegularizationPage — Submit & track attendance regularization requests.
 *
 * Features:
 *  • Form to submit a regularization request (date, requested status, reason)
 *  • List of past regularization requests with status badges
 *  • Filter by status (all / pending / approved / rejected)
 */

import { useCallback, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileEdit,
  Plus,
  Clock,
  CheckCircle2,
  XCircle,
  Hourglass,
  AlertCircle,
  X,
  Send,
  CalendarDays,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import * as attendanceApi from "@/api/attendance";
import type {
  AttendanceStatus,
  RegularizationRecord,
  RegularizationStatus,
} from "@/api/attendance";

// ── Helpers ────────────────────────────────────────────────────────

const REG_STATUS_CONFIG: Record<
  RegularizationStatus,
  { label: string; icon: React.ReactNode; bg: string; text: string }
> = {
  pending: {
    label: "Pending",
    icon: <Hourglass className="h-3.5 w-3.5" />,
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
  },
  approved: {
    label: "Approved",
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
  },
  rejected: {
    label: "Rejected",
    icon: <XCircle className="h-3.5 w-3.5" />,
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
  },
};

const REQUESTED_STATUS_OPTIONS: {
  value: AttendanceStatus;
  label: string;
}[] = [
  { value: "present", label: "Present" },
  { value: "half_day", label: "Half Day" },
  { value: "work_from_home", label: "Work From Home" },
  { value: "on_duty", label: "On Duty" },
];

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

// ── Component ──────────────────────────────────────────────────────

export function RegularizationPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<RegularizationStatus | "all">("all");

  // Form state
  const [formDate, setFormDate] = useState("");
  const [formStatus, setFormStatus] = useState<AttendanceStatus>("present");
  const [formReason, setFormReason] = useState("");
  const [formClockIn, setFormClockIn] = useState("");
  const [formClockOut, setFormClockOut] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  // ── Data fetching ────────────────────────────────────────────────

  const { data: regData, isLoading } = useQuery({
    queryKey: [
      "regularizations",
      statusFilter === "all" ? undefined : statusFilter,
    ],
    queryFn: () =>
      attendanceApi.getRegularizations({
        status: statusFilter === "all" ? undefined : statusFilter,
        page: 1,
        page_size: 50,
      }),
  });

  // ── Submit mutation ──────────────────────────────────────────────

  const submitMut = useMutation({
    mutationFn: (body: {
      date: string;
      requested_status: AttendanceStatus;
      reason: string;
      requested_clock_in?: string;
      requested_clock_out?: string;
    }) => attendanceApi.submitRegularization(body),
    onSuccess: () => {
      setShowForm(false);
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["regularizations"] });
    },
    onError: (err: any) => {
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.errors?.date?.[0] ||
        err?.message ||
        "Failed to submit regularization";
      setFormError(typeof detail === "string" ? detail : JSON.stringify(detail));
    },
  });

  const resetForm = useCallback(() => {
    setFormDate("");
    setFormStatus("present");
    setFormReason("");
    setFormClockIn("");
    setFormClockOut("");
    setFormError(null);
  }, []);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setFormError(null);

      if (!formDate) {
        setFormError("Please select a date.");
        return;
      }
      if (formReason.trim().length < 10) {
        setFormError("Reason must be at least 10 characters.");
        return;
      }

      const body: {
        date: string;
        requested_status: AttendanceStatus;
        reason: string;
        requested_clock_in?: string;
        requested_clock_out?: string;
      } = {
        date: formDate,
        requested_status: formStatus,
        reason: formReason.trim(),
      };

      if (formClockIn) {
        body.requested_clock_in = `${formDate}T${formClockIn}:00`;
      }
      if (formClockOut) {
        body.requested_clock_out = `${formDate}T${formClockOut}:00`;
      }

      submitMut.mutate(body);
    },
    [formDate, formStatus, formReason, formClockIn, formClockOut, submitMut],
  );

  // ── Stats ────────────────────────────────────────────────────────

  const stats = useMemo(() => {
    const items = regData?.data ?? [];
    return {
      total: items.length,
      pending: items.filter((r) => r.status === "pending").length,
      approved: items.filter((r) => r.status === "approved").length,
      rejected: items.filter((r) => r.status === "rejected").length,
    };
  }, [regData]);

  // Yesterday as max date for the date input
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const maxDate = toDateStr(yesterday);

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">
            Attendance Regularization
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Request corrections to your attendance records
          </p>
        </div>
        <Button
          onClick={() => {
            setShowForm(!showForm);
            if (!showForm) resetForm();
          }}
          className="gap-1.5 shrink-0"
        >
          {showForm ? (
            <>
              <X className="h-4 w-4" />
              Cancel
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" />
              New Request
            </>
          )}
        </Button>
      </div>

      {/* New Request Form */}
      {showForm && (
        <Card className="border-primary/20 shadow-md">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileEdit className="h-4 w-4 text-primary" />
              Submit Regularization Request
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                {/* Date */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Date <span className="text-red-500">*</span>
                  </label>
                  <input
                    type="date"
                    value={formDate}
                    max={maxDate}
                    onChange={(e) => setFormDate(e.target.value)}
                    className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
                  />
                  <p className="text-xs text-muted-foreground">
                    Only past dates can be regularized
                  </p>
                </div>

                {/* Requested Status */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Requested Status <span className="text-red-500">*</span>
                  </label>
                  <select
                    value={formStatus}
                    onChange={(e) =>
                      setFormStatus(e.target.value as AttendanceStatus)
                    }
                    className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
                  >
                    {REQUESTED_STATUS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Clock In Time (optional) */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Clock In Time{" "}
                    <span className="text-xs text-muted-foreground">
                      (optional)
                    </span>
                  </label>
                  <input
                    type="time"
                    value={formClockIn}
                    onChange={(e) => setFormClockIn(e.target.value)}
                    className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
                  />
                </div>

                {/* Clock Out Time (optional) */}
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Clock Out Time{" "}
                    <span className="text-xs text-muted-foreground">
                      (optional)
                    </span>
                  </label>
                  <input
                    type="time"
                    value={formClockOut}
                    onChange={(e) => setFormClockOut(e.target.value)}
                    className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
                  />
                </div>
              </div>

              {/* Reason */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium text-foreground">
                  Reason <span className="text-red-500">*</span>
                </label>
                <textarea
                  value={formReason}
                  onChange={(e) => setFormReason(e.target.value)}
                  rows={3}
                  maxLength={500}
                  placeholder="Explain why you need this attendance record corrected (min 10 characters)…"
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground resize-none focus:border-ring focus:ring-2 focus:ring-ring/20"
                />
                <div className="flex justify-between">
                  <p className="text-xs text-muted-foreground">
                    Min 10 characters
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formReason.length}/500
                  </p>
                </div>
              </div>

              {/* Error */}
              {formError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {formError}
                </div>
              )}

              {/* Submit */}
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setShowForm(false);
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={submitMut.isPending}
                  className="gap-1.5"
                >
                  <Send className="h-4 w-4" />
                  {submitMut.isPending ? "Submitting…" : "Submit Request"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Filter Tabs */}
      <div className="flex items-center gap-1 rounded-lg bg-muted p-1 w-fit">
        {(
          [
            { value: "all", label: "All", count: stats.total },
            { value: "pending", label: "Pending", count: stats.pending },
            { value: "approved", label: "Approved", count: stats.approved },
            { value: "rejected", label: "Rejected", count: stats.rejected },
          ] as const
        ).map((tab) => (
          <button
            key={tab.value}
            onClick={() =>
              setStatusFilter(tab.value as RegularizationStatus | "all")
            }
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
              statusFilter === tab.value
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
            <span
              className={cn(
                "inline-flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[10px] font-semibold tabular-nums",
                statusFilter === tab.value
                  ? "bg-primary/10 text-primary"
                  : "bg-muted-foreground/10 text-muted-foreground",
              )}
            >
              {tab.count}
            </span>
          </button>
        ))}
      </div>

      {/* Requests List */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarDays className="h-4 w-4 text-primary" />
            Regularization Requests
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            </div>
          ) : !regData?.data.length ? (
            <div className="flex flex-col items-center justify-center py-16">
              <FileEdit className="h-10 w-10 text-muted-foreground/30" />
              <p className="mt-3 text-sm text-muted-foreground">
                {statusFilter === "all"
                  ? "No regularization requests yet"
                  : `No ${statusFilter} requests`}
              </p>
              {statusFilter === "all" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3 gap-1.5"
                  onClick={() => {
                    setShowForm(true);
                    resetForm();
                  }}
                >
                  <Plus className="h-3.5 w-3.5" />
                  Submit Your First Request
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {regData.data.map((reg: RegularizationRecord) => {
                const cfg = REG_STATUS_CONFIG[reg.status];
                const reqStatusLabel =
                  REQUESTED_STATUS_OPTIONS.find(
                    (o) => o.value === reg.requested_status,
                  )?.label ?? reg.requested_status;

                return (
                  <div
                    key={reg.id}
                    className={cn(
                      "rounded-lg border p-4 transition-colors",
                      reg.status === "pending"
                        ? "border-amber-200 bg-amber-50/30"
                        : "border-border",
                    )}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        {/* Date & requested status */}
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold text-foreground">
                            {formatDate(reg.created_at)}
                          </span>
                          <span className="text-muted-foreground">→</span>
                          <Badge
                            variant="secondary"
                            className="text-xs font-medium"
                          >
                            {reqStatusLabel}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            for {formatDate(reg.created_at)}
                          </span>
                        </div>

                        {/* Reason */}
                        <p className="mt-1.5 text-sm text-muted-foreground line-clamp-2">
                          {reg.reason}
                        </p>

                        {/* Reviewer remarks (if rejected) */}
                        {reg.reviewer_remarks && (
                          <div className="mt-2 flex items-start gap-2 rounded-md bg-red-50 border border-red-100 px-3 py-2">
                            <AlertCircle className="h-3.5 w-3.5 mt-0.5 text-red-500 shrink-0" />
                            <p className="text-xs text-red-700">
                              <span className="font-medium">
                                Reviewer remarks:
                              </span>{" "}
                              {reg.reviewer_remarks}
                            </p>
                          </div>
                        )}

                        {/* Timestamps */}
                        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            Submitted {formatDate(reg.created_at)}
                          </span>
                          {reg.reviewed_at && (
                            <span className="flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" />
                              Reviewed {formatDate(reg.reviewed_at)}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Status badge */}
                      <Badge
                        className={cn(
                          "border text-xs gap-1 shrink-0",
                          cfg.bg,
                          cfg.text,
                        )}
                      >
                        {cfg.icon}
                        {cfg.label}
                      </Badge>
                    </div>
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
