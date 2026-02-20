/**
 * LeavePage — Employee leave self-service.
 *
 * Features:
 *  • Leave balance cards (CL, EL, SL, etc.) with used/total + progress bars
 *  • Apply leave form with date picker, leave type, reason, half-day toggle
 *  • My leave requests table with status badges (pending=yellow, approved=green, rejected=red)
 */

import { useCallback, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Calendar,
  Plus,
  X,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Send,
  CalendarDays,
  TreePalm,
  Stethoscope,
  Briefcase,
  Baby,
  ChevronLeft,
  ChevronRight,
  Filter,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import * as leaveApi from "@/api/leave";
import type { LeaveBalance, LeaveDayType, LeaveRequest, LeaveStatus, LeaveType } from "@/api/leave";

// ── Helpers ────────────────────────────────────────────────────────

function toDateInputStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const STATUS_CONFIG: Record<
  LeaveStatus,
  { label: string; bg: string; text: string; icon: typeof Clock }
> = {
  pending: {
    label: "Pending",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
    icon: Clock,
  },
  approved: {
    label: "Approved",
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
    icon: CheckCircle2,
  },
  rejected: {
    label: "Rejected",
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
    icon: XCircle,
  },
  cancelled: {
    label: "Cancelled",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    icon: X,
  },
  revoked: {
    label: "Revoked",
    bg: "bg-slate-100 border-slate-300",
    text: "text-slate-700",
    icon: XCircle,
  },
};

const LEAVE_ICONS: Record<string, typeof Calendar> = {
  CL: TreePalm,
  EL: Briefcase,
  SL: Stethoscope,
  ML: Baby,
  PL: Baby,
  CO: CalendarDays,
};

const LEAVE_COLORS: Record<string, { gradient: string; bar: string; iconBg: string }> = {
  CL: { gradient: "from-violet-50 to-purple-50", bar: "bg-violet-500", iconBg: "bg-violet-100 text-violet-600" },
  EL: { gradient: "from-blue-50 to-indigo-50", bar: "bg-blue-500", iconBg: "bg-blue-100 text-blue-600" },
  SL: { gradient: "from-emerald-50 to-teal-50", bar: "bg-emerald-500", iconBg: "bg-emerald-100 text-emerald-600" },
  ML: { gradient: "from-pink-50 to-rose-50", bar: "bg-pink-500", iconBg: "bg-pink-100 text-pink-600" },
  PL: { gradient: "from-pink-50 to-rose-50", bar: "bg-pink-500", iconBg: "bg-pink-100 text-pink-600" },
  CO: { gradient: "from-amber-50 to-orange-50", bar: "bg-amber-500", iconBg: "bg-amber-100 text-amber-600" },
};

const DEFAULT_COLOR = { gradient: "from-slate-50 to-gray-50", bar: "bg-primary", iconBg: "bg-primary/10 text-primary" };

// ── Component ──────────────────────────────────────────────────────

export function LeavePage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<LeaveStatus | "all">("all");
  const [page, setPage] = useState(1);

  // ── Data fetching ────────────────────────────────────────────────

  const { data: balances, isLoading: loadingBalances } = useQuery({
    queryKey: ["leaveBalances"],
    queryFn: () => leaveApi.getBalances(),
  });

  const { data: policies } = useQuery({
    queryKey: ["leavePolicies"],
    queryFn: () => leaveApi.getPolicies(true),
  });

  const { data: myLeaves, isLoading: loadingLeaves } = useQuery({
    queryKey: ["myLeaves", statusFilter, page],
    queryFn: () =>
      leaveApi.getMyLeaves({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 10,
      }),
  });

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Leave Management</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            View balances, apply for leave, and track your requests
          </p>
        </div>
        <Button
          onClick={() => setShowForm(!showForm)}
          className="gap-2 shadow-md"
        >
          {showForm ? (
            <>
              <X className="h-4 w-4" /> Cancel
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> Apply Leave
            </>
          )}
        </Button>
      </div>

      {/* Leave Balance Cards */}
      <div>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Leave Balances
        </h3>
        {loadingBalances ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {balances?.map((balance) => (
              <BalanceCard key={balance.id} balance={balance} />
            ))}
            {balances?.length === 0 && (
              <Card className="col-span-full">
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Calendar className="h-10 w-10 text-muted-foreground/40" />
                  <p className="mt-3 text-sm text-muted-foreground">
                    No leave balances found for this year
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        )}
      </div>

      {/* Apply Leave Form */}
      {showForm && (
        <ApplyLeaveForm
          policies={policies || []}
          balances={balances || []}
          onSuccess={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["leaveBalances"] });
            queryClient.invalidateQueries({ queryKey: ["myLeaves"] });
          }}
        />
      )}

      {/* My Leave Requests */}
      <div>
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            My Leave Requests
          </h3>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <div className="flex gap-1">
              {(["all", "pending", "approved", "rejected"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => { setStatusFilter(s); setPage(1); }}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                    statusFilter === s
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80",
                  )}
                >
                  {s === "all" ? "All" : STATUS_CONFIG[s].label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loadingLeaves ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {myLeaves?.data.map((req) => (
                <LeaveRequestCard key={req.id} request={req} />
              ))}
              {myLeaves?.data.length === 0 && (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <Calendar className="h-10 w-10 text-muted-foreground/40" />
                    <p className="mt-3 text-sm text-muted-foreground">
                      No leave requests found
                    </p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Pagination */}
            {myLeaves && myLeaves.meta.total_pages > 1 && (
              <div className="mt-4 flex items-center justify-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!myLeaves.meta.has_prev}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </Button>
                <span className="text-sm text-muted-foreground">
                  Page {myLeaves.meta.page} of {myLeaves.meta.total_pages}
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!myLeaves.meta.has_next}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

// ── Balance Card ───────────────────────────────────────────────────

function BalanceCard({ balance }: { balance: LeaveBalance }) {
  const code = balance.leave_type?.code || "??";
  const name = balance.leave_type?.name || "Unknown";
  const colors = LEAVE_COLORS[code] || DEFAULT_COLOR;
  const Icon = LEAVE_ICONS[code] || Calendar;

  const total = Number(balance.current_balance) + Number(balance.used);
  const used = Number(balance.used);
  const available = Number(balance.available);
  const pending = Number(balance.pending);
  const pct = total > 0 ? Math.min((used / total) * 100, 100) : 0;

  return (
    <Card className={cn("overflow-hidden border-0 shadow-sm")}>
      <CardContent className={cn("bg-gradient-to-br p-5", colors.gradient)}>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className={cn("rounded-lg p-2", colors.iconBg)}>
              <Icon className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">{name}</p>
              <p className="text-xs text-muted-foreground">{code}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-2xl font-bold tabular-nums text-foreground">{available}</p>
            <p className="text-xs text-muted-foreground">available</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-4">
          <div className="h-2 w-full overflow-hidden rounded-full bg-white/60">
            <div
              className={cn("h-full rounded-full transition-all", colors.bar)}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-2 flex justify-between text-xs text-muted-foreground">
            <span>{used} used</span>
            {pending > 0 && (
              <span className="text-amber-600">{pending} pending</span>
            )}
            <span>{total} total</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Apply Leave Form ───────────────────────────────────────────────

function ApplyLeaveForm({
  policies,
  balances,
  onSuccess,
}: {
  policies: LeaveType[];
  balances: LeaveBalance[];
  onSuccess: () => void;
}) {
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [reason, setReason] = useState("");
  const [halfDay, setHalfDay] = useState(false);
  const [halfDayType, setHalfDayType] = useState<"first_half" | "second_half">("first_half");
  const [error, setError] = useState<string | null>(null);

  const today = toDateInputStr(new Date());

  const selectedPolicy = policies.find((p) => p.id === leaveTypeId);
  const selectedBalance = balances.find((b) => b.leave_type_id === leaveTypeId);

  // Calculate number of days
  const dayCount = useMemo(() => {
    if (!fromDate || !toDate) return 0;
    const from = new Date(fromDate);
    const to = new Date(toDate);
    if (to < from) return 0;
    const diffMs = to.getTime() - from.getTime();
    let days = Math.floor(diffMs / (1000 * 60 * 60 * 24)) + 1;
    if (halfDay && days === 1) days = 0.5;
    return days;
  }, [fromDate, toDate, halfDay]);

  const applyMut = useMutation({
    mutationFn: leaveApi.applyLeave,
    onSuccess: () => {
      setError(null);
      onSuccess();
    },
    onError: (err: any) => {
      setError(
        err?.response?.data?.detail || err?.message || "Failed to apply leave",
      );
    },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      if (!leaveTypeId) {
        setError("Please select a leave type");
        return;
      }
      if (!fromDate || !toDate) {
        setError("Please select start and end dates");
        return;
      }
      if (new Date(toDate) < new Date(fromDate)) {
        setError("End date must be on or after start date");
        return;
      }

      // Build day_details for half-day
      let day_details: Record<string, LeaveDayType> | undefined;
      if (halfDay && fromDate === toDate) {
        day_details = { [fromDate]: halfDayType };
      }

      applyMut.mutate({
        leave_type_id: leaveTypeId,
        from_date: fromDate,
        to_date: toDate,
        reason: reason || undefined,
        day_details,
      });
    },
    [leaveTypeId, fromDate, toDate, reason, halfDay, halfDayType, applyMut],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Send className="h-5 w-5 text-primary" />
          Apply for Leave
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            {/* Leave Type */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                Leave Type <span className="text-red-500">*</span>
              </label>
              <select
                value={leaveTypeId}
                onChange={(e) => setLeaveTypeId(e.target.value)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="">Select leave type</option>
                {policies.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.code})
                  </option>
                ))}
              </select>
              {selectedBalance && (
                <p className="text-xs text-muted-foreground">
                  Available: <span className="font-medium text-foreground">{Number(selectedBalance.available)}</span> days
                </p>
              )}
            </div>

            {/* Days summary */}
            <div className="flex items-center justify-center rounded-lg bg-primary/5 p-4">
              <div className="text-center">
                <p className="text-3xl font-bold tabular-nums text-primary">{dayCount}</p>
                <p className="text-sm text-muted-foreground">
                  {dayCount === 1 ? "day" : "days"} requested
                </p>
              </div>
            </div>

            {/* From Date */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                From Date <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => {
                  setFromDate(e.target.value);
                  if (!toDate || e.target.value > toDate) setToDate(e.target.value);
                }}
                min={today}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            {/* To Date */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                To Date <span className="text-red-500">*</span>
              </label>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                min={fromDate || today}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            {/* Half Day Toggle */}
            {fromDate && toDate && fromDate === toDate && (
              <div className="space-y-1.5 sm:col-span-2">
                <div className="flex items-center gap-3">
                  <label className="relative inline-flex cursor-pointer items-center">
                    <input
                      type="checkbox"
                      checked={halfDay}
                      onChange={(e) => setHalfDay(e.target.checked)}
                      className="peer sr-only"
                    />
                    <div className="h-5 w-9 rounded-full bg-muted peer-checked:bg-primary after:absolute after:left-[2px] after:top-[2px] after:h-4 after:w-4 after:rounded-full after:border after:border-muted after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white" />
                  </label>
                  <span className="text-sm font-medium text-foreground">Half Day</span>
                </div>
                {halfDay && (
                  <div className="ml-12 flex gap-3">
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="halfDayType"
                        checked={halfDayType === "first_half"}
                        onChange={() => setHalfDayType("first_half")}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className="text-sm text-foreground">First Half</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="radio"
                        name="halfDayType"
                        checked={halfDayType === "second_half"}
                        onChange={() => setHalfDayType("second_half")}
                        className="h-4 w-4 accent-primary"
                      />
                      <span className="text-sm text-foreground">Second Half</span>
                    </label>
                  </div>
                )}
              </div>
            )}

            {/* Reason */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">Reason</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Provide a reason for your leave request..."
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              />
            </div>
          </div>

          {/* Policy info */}
          {selectedPolicy && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3">
              <p className="text-xs text-blue-700">
                <span className="font-medium">Policy info:</span>{" "}
                {selectedPolicy.min_days_notice > 0 && (
                  <span>Min {selectedPolicy.min_days_notice} days notice required. </span>
                )}
                {selectedPolicy.max_consecutive_days && (
                  <span>Max {selectedPolicy.max_consecutive_days} consecutive days. </span>
                )}
                {selectedPolicy.requires_approval && <span>Requires manager approval. </span>}
                {!selectedPolicy.is_paid && (
                  <span className="font-medium text-amber-700">Unpaid leave. </span>
                )}
              </p>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={applyMut.isPending}
              className="gap-2 min-w-[140px]"
            >
              <Send className="h-4 w-4" />
              {applyMut.isPending ? "Submitting…" : "Submit Request"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Leave Request Card ─────────────────────────────────────────────

function LeaveRequestCard({ request }: { request: LeaveRequest }) {
  const cfg = STATUS_CONFIG[request.status];
  const StatusIcon = cfg.icon;
  const leaveCode = request.leave_type?.code || "—";
  const leaveName = request.leave_type?.name || "Leave";

  return (
    <Card className="overflow-hidden transition-shadow hover:shadow-md">
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Left: leave info */}
          <div className="flex items-start gap-3">
            <div
              className={cn(
                "mt-0.5 rounded-lg p-2",
                (LEAVE_COLORS[leaveCode] || DEFAULT_COLOR).iconBg,
              )}
            >
              {(() => {
                const Icon = LEAVE_ICONS[leaveCode] || Calendar;
                return <Icon className="h-4 w-4" />;
              })()}
            </div>
            <div>
              <p className="font-semibold text-foreground">
                {leaveName}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                  ({leaveCode})
                </span>
              </p>
              <p className="mt-0.5 text-sm text-muted-foreground">
                {formatDate(request.start_date)}
                {request.start_date !== request.end_date && (
                  <> → {formatDate(request.end_date)}</>
                )}
                <span className="ml-2 font-medium text-foreground">
                  {Number(request.total_days)} {Number(request.total_days) === 1 ? "day" : "days"}
                </span>
              </p>
              {request.reason && (
                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                  {request.reason}
                </p>
              )}
            </div>
          </div>

          {/* Right: status + date */}
          <div className="flex items-center gap-3 sm:flex-col sm:items-end">
            <Badge
              className={cn("gap-1 border text-xs", cfg.bg, cfg.text)}
            >
              <StatusIcon className="h-3 w-3" />
              {cfg.label}
            </Badge>
            <span className="text-xs text-muted-foreground">
              Applied {formatDate(request.created_at)}
            </span>
            {request.reviewer_remarks && (
              <p className="text-xs text-muted-foreground italic max-w-[200px] truncate">
                "{request.reviewer_remarks}"
              </p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
