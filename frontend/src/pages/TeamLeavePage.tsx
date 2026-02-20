/**
 * TeamLeavePage — Manager view for team leave requests.
 *
 * Features:
 *  • Summary cards (pending, approved, rejected counts)
 *  • Team leave requests list with employee info
 *  • Approve / reject actions with confirmation
 *  • Filterable by status
 */

import { useCallback, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ThumbsUp,
  ThumbsDown,
  Calendar,
  Filter,
  ChevronLeft,
  ChevronRight,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn, formatDate, getInitials } from "@/lib/utils";
import * as leaveApi from "@/api/leave";
import type { LeaveRequest, LeaveStatus } from "@/api/leave";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  LeaveStatus,
  { label: string; bg: string; text: string; dot: string }
> = {
  pending: {
    label: "Pending",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
    dot: "bg-amber-500",
  },
  approved: {
    label: "Approved",
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
    dot: "bg-emerald-500",
  },
  rejected: {
    label: "Rejected",
    bg: "bg-red-50 border-red-200",
    text: "text-red-700",
    dot: "bg-red-500",
  },
  cancelled: {
    label: "Cancelled",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    dot: "bg-slate-400",
  },
  revoked: {
    label: "Revoked",
    bg: "bg-slate-100 border-slate-300",
    text: "text-slate-700",
    dot: "bg-slate-500",
  },
};

// ── Component ──────────────────────────────────────────────────────

export function TeamLeavePage() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<LeaveStatus | "all">("pending");
  const [page, setPage] = useState(1);
  const [actionTarget, setActionTarget] = useState<{
    id: string;
    action: "approve" | "reject";
    name: string;
  } | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [approveRemarks, setApproveRemarks] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  // ── Data fetching ────────────────────────────────────────────────

  const { data: teamLeaves, isLoading } = useQuery({
    queryKey: ["teamLeaves", statusFilter, page],
    queryFn: () =>
      leaveApi.getTeamLeaves({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 15,
      }),
  });

  // Fetch summary counts
  const { data: pendingData } = useQuery({
    queryKey: ["teamLeaves", "pending", "count"],
    queryFn: () => leaveApi.getTeamLeaves({ status: "pending", page: 1, page_size: 1 }),
  });
  const { data: approvedData } = useQuery({
    queryKey: ["teamLeaves", "approved", "count"],
    queryFn: () => leaveApi.getTeamLeaves({ status: "approved", page: 1, page_size: 1 }),
  });
  const { data: rejectedData } = useQuery({
    queryKey: ["teamLeaves", "rejected", "count"],
    queryFn: () => leaveApi.getTeamLeaves({ status: "rejected", page: 1, page_size: 1 }),
  });

  // ── Mutations ────────────────────────────────────────────────────

  const approveMut = useMutation({
    mutationFn: ({ id, remarks }: { id: string; remarks?: string }) =>
      leaveApi.approveLeave(id, remarks),
    onSuccess: () => {
      setActionTarget(null);
      setApproveRemarks("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["teamLeaves"] });
    },
    onError: (err: any) => {
      setActionError(
        err?.response?.data?.detail || err?.message || "Failed to approve",
      );
    },
  });

  const rejectMut = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      leaveApi.rejectLeave(id, reason),
    onSuccess: () => {
      setActionTarget(null);
      setRejectReason("");
      setActionError(null);
      queryClient.invalidateQueries({ queryKey: ["teamLeaves"] });
    },
    onError: (err: any) => {
      setActionError(
        err?.response?.data?.detail || err?.message || "Failed to reject",
      );
    },
  });

  const handleAction = useCallback(() => {
    if (!actionTarget) return;
    setActionError(null);

    if (actionTarget.action === "approve") {
      approveMut.mutate({
        id: actionTarget.id,
        remarks: approveRemarks || undefined,
      });
    } else {
      if (rejectReason.trim().length < 5) {
        setActionError("Rejection reason must be at least 5 characters");
        return;
      }
      rejectMut.mutate({ id: actionTarget.id, reason: rejectReason.trim() });
    }
  }, [actionTarget, approveRemarks, rejectReason, approveMut, rejectMut]);

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Team Leave Requests</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Review and manage leave requests from your team
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-3">
        <SummaryCard
          icon={<Clock className="h-5 w-5 text-amber-600" />}
          label="Pending"
          count={pendingData?.meta.total ?? 0}
          color="text-amber-700"
          bg="bg-amber-50"
          active={statusFilter === "pending"}
          onClick={() => { setStatusFilter("pending"); setPage(1); }}
        />
        <SummaryCard
          icon={<CheckCircle2 className="h-5 w-5 text-emerald-600" />}
          label="Approved"
          count={approvedData?.meta.total ?? 0}
          color="text-emerald-700"
          bg="bg-emerald-50"
          active={statusFilter === "approved"}
          onClick={() => { setStatusFilter("approved"); setPage(1); }}
        />
        <SummaryCard
          icon={<XCircle className="h-5 w-5 text-red-500" />}
          label="Rejected"
          count={rejectedData?.meta.total ?? 0}
          color="text-red-600"
          bg="bg-red-50"
          active={statusFilter === "rejected"}
          onClick={() => { setStatusFilter("rejected"); setPage(1); }}
        />
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-muted-foreground" />
        <div className="flex gap-1">
          {(["all", "pending", "approved", "rejected", "cancelled"] as const).map(
            (s) => (
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
            ),
          )}
        </div>
      </div>

      {/* Requests list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {teamLeaves?.data.map((req) => (
              <TeamLeaveCard
                key={req.id}
                request={req}
                onApprove={() =>
                  setActionTarget({
                    id: req.id,
                    action: "approve",
                    name: req.employee?.display_name || "Employee",
                  })
                }
                onReject={() =>
                  setActionTarget({
                    id: req.id,
                    action: "reject",
                    name: req.employee?.display_name || "Employee",
                  })
                }
              />
            ))}
            {teamLeaves?.data.length === 0 && (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-16">
                  <Users className="h-12 w-12 text-muted-foreground/40" />
                  <h3 className="mt-4 text-lg font-medium text-foreground">
                    No requests found
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {statusFilter === "pending"
                      ? "All caught up! No pending leave requests."
                      : "No leave requests match the current filter."}
                  </p>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Pagination */}
          {teamLeaves && teamLeaves.meta.total_pages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!teamLeaves.meta.has_prev}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {teamLeaves.meta.page} of {teamLeaves.meta.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!teamLeaves.meta.has_next}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}

      {/* Action Modal */}
      {actionTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <Card className="w-full max-w-md shadow-xl">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-2">
                  {actionTarget.action === "approve" ? (
                    <>
                      <ThumbsUp className="h-5 w-5 text-emerald-600" />
                      Approve Leave
                    </>
                  ) : (
                    <>
                      <ThumbsDown className="h-5 w-5 text-red-500" />
                      Reject Leave
                    </>
                  )}
                </CardTitle>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => {
                    setActionTarget(null);
                    setActionError(null);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-muted-foreground">
                {actionTarget.action === "approve"
                  ? `Are you sure you want to approve the leave request from ${actionTarget.name}?`
                  : `Please provide a reason for rejecting ${actionTarget.name}'s leave request.`}
              </p>

              {actionTarget.action === "approve" ? (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Remarks (optional)
                  </label>
                  <textarea
                    value={approveRemarks}
                    onChange={(e) => setApproveRemarks(e.target.value)}
                    placeholder="Add any remarks..."
                    rows={2}
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                  />
                </div>
              ) : (
                <div className="space-y-1.5">
                  <label className="text-sm font-medium text-foreground">
                    Reason <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Explain why this leave request is being rejected..."
                    rows={3}
                    className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                  />
                </div>
              )}

              {actionError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  {actionError}
                </div>
              )}

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => {
                    setActionTarget(null);
                    setActionError(null);
                  }}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleAction}
                  disabled={approveMut.isPending || rejectMut.isPending}
                  className={cn(
                    actionTarget.action === "approve"
                      ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                      : "bg-red-500 hover:bg-red-600 text-white",
                  )}
                >
                  {actionTarget.action === "approve" ? (
                    <>
                      <ThumbsUp className="h-4 w-4" />
                      {approveMut.isPending ? "Approving…" : "Approve"}
                    </>
                  ) : (
                    <>
                      <ThumbsDown className="h-4 w-4" />
                      {rejectMut.isPending ? "Rejecting…" : "Reject"}
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

// ── Summary Card ───────────────────────────────────────────────────

function SummaryCard({
  icon,
  label,
  count,
  color,
  bg,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  color: string;
  bg: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        active && "ring-2 ring-primary ring-offset-2",
      )}
      onClick={onClick}
    >
      <CardContent className="flex items-center gap-4 p-5">
        <div className={cn("rounded-lg p-2.5", bg)}>{icon}</div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className={cn("text-2xl font-bold tabular-nums", color)}>{count}</p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Team Leave Card ────────────────────────────────────────────────

function TeamLeaveCard({
  request,
  onApprove,
  onReject,
}: {
  request: LeaveRequest;
  onApprove: () => void;
  onReject: () => void;
}) {
  const cfg = STATUS_CONFIG[request.status];
  const emp = request.employee;
  const isPending = request.status === "pending";

  return (
    <Card className="overflow-hidden transition-shadow hover:shadow-md">
      <CardContent className="p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          {/* Employee info + leave details */}
          <div className="flex items-start gap-3">
            <Avatar size="lg">
              {emp?.profile_photo_url && (
                <AvatarImage src={emp.profile_photo_url} alt={emp.display_name || ""} />
              )}
              <AvatarFallback>
                {getInitials(emp?.display_name || "??")}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="font-semibold text-foreground truncate">
                  {emp?.display_name || "Unknown"}
                </p>
                <Badge className={cn("border text-xs", cfg.bg, cfg.text)}>
                  {cfg.label}
                </Badge>
              </div>
              {emp?.designation && (
                <p className="text-xs text-muted-foreground">
                  {emp.designation}
                  {emp.department_name && ` · ${emp.department_name}`}
                </p>
              )}
              <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Calendar className="h-3.5 w-3.5" />
                  {formatDate(request.start_date)}
                  {request.start_date !== request.end_date && (
                    <> → {formatDate(request.end_date)}</>
                  )}
                </span>
                <span className="font-medium text-foreground">
                  {Number(request.total_days)} {Number(request.total_days) === 1 ? "day" : "days"}
                </span>
                {request.leave_type && (
                  <Badge variant="secondary" className="text-xs">
                    {request.leave_type.name}
                  </Badge>
                )}
              </div>
              {request.reason && (
                <p className="mt-1 text-sm text-muted-foreground line-clamp-2">
                  {request.reason}
                </p>
              )}
            </div>
          </div>

          {/* Actions */}
          {isPending && (
            <div className="flex shrink-0 gap-2 sm:flex-col">
              <Button
                size="sm"
                onClick={onApprove}
                className="gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <ThumbsUp className="h-3.5 w-3.5" />
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onReject}
                className="gap-1.5 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
              >
                <ThumbsDown className="h-3.5 w-3.5" />
                Reject
              </Button>
            </div>
          )}
          {!isPending && request.reviewed_at && (
            <div className="text-right text-xs text-muted-foreground">
              <p>
                {request.status === "approved" ? "Approved" : "Rejected"}{" "}
                {formatDate(request.reviewed_at)}
              </p>
              {request.reviewer_remarks && (
                <p className="mt-0.5 italic max-w-[180px] truncate">
                  "{request.reviewer_remarks}"
                </p>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
