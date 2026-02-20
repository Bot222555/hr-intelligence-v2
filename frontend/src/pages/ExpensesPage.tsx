/**
 * ExpensesPage — Employee expense claims management.
 *
 * Features:
 *  • Expense claim list with status filters
 *  • Create new expense claim form (title, amount, remarks)
 *  • Approval flow view for managers
 */

import { useCallback, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Receipt,
  Plus,
  X,
  Send,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Filter,
  Users,
  ArrowDownToLine,
  Ban,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { ADMIN_ROLES, ROLES } from "@/lib/constants";
import * as expensesApi from "@/api/expenses";
import type { ExpenseClaim } from "@/api/expenses";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  string,
  { label: string; bg: string; text: string; icon: typeof Clock }
> = {
  draft: {
    label: "Draft",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    icon: Receipt,
  },
  pending: {
    label: "Pending",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
    icon: Clock,
  },
  submitted: {
    label: "Submitted",
    bg: "bg-blue-50 border-blue-200",
    text: "text-blue-700",
    icon: Send,
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
  reimbursed: {
    label: "Reimbursed",
    bg: "bg-violet-50 border-violet-200",
    text: "text-violet-700",
    icon: ArrowDownToLine,
  },
};

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

function getClaimStatus(claim: ExpenseClaim): string {
  return claim.approval_status || "pending";
}

// ── Component ──────────────────────────────────────────────────────

export function ExpensesPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isManager =
    user &&
    (user.role === ROLES.MANAGER ||
      ADMIN_ROLES.includes(user.role as (typeof ADMIN_ROLES)[number]));

  const [activeTab, setActiveTab] = useState<"my" | "team">("my");
  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [selectedClaim, setSelectedClaim] = useState<ExpenseClaim | null>(null);

  // ── Queries ────────────────────────────────────────────────────

  const { data: myExpenses, isLoading: loadingMy } = useQuery({
    queryKey: ["myExpenses", statusFilter, page],
    queryFn: () =>
      expensesApi.getMyExpenses({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 10,
      }),
    enabled: activeTab === "my",
  });

  const { data: teamExpenses, isLoading: loadingTeam } = useQuery({
    queryKey: ["teamExpenses", statusFilter, page],
    queryFn: () =>
      expensesApi.getTeamExpenses({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 10,
      }),
    enabled: activeTab === "team" && !!isManager,
  });

  const activeData = activeTab === "my" ? myExpenses : teamExpenses;
  const isLoading = activeTab === "my" ? loadingMy : loadingTeam;

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Expenses</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Submit expense claims and track reimbursements
          </p>
        </div>
        <Button
          onClick={() => {
            setShowForm(!showForm);
            if (showForm) setSelectedClaim(null);
          }}
          className="gap-2 shadow-md"
        >
          {showForm ? (
            <>
              <X className="h-4 w-4" /> Cancel
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> New Claim
            </>
          )}
        </Button>
      </div>

      {/* Tab navigation for manager */}
      {isManager && (
        <div className="flex items-center gap-1 rounded-lg bg-muted p-1 w-fit">
          <button
            onClick={() => { setActiveTab("my"); setPage(1); }}
            className={cn(
              "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all",
              activeTab === "my"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Receipt className="h-4 w-4" />
            My Claims
          </button>
          <button
            onClick={() => { setActiveTab("team"); setPage(1); }}
            className={cn(
              "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all",
              activeTab === "team"
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Users className="h-4 w-4" />
            Team Claims
          </button>
        </div>
      )}

      {/* Create Expense Form */}
      {showForm && (
        <CreateExpenseForm
          onSuccess={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["myExpenses"] });
          }}
        />
      )}

      {/* Claim Detail View */}
      {selectedClaim && !showForm && (
        <ClaimDetailView
          claim={selectedClaim}
          isManager={!!isManager && activeTab === "team"}
          onClose={() => setSelectedClaim(null)}
          onUpdate={() => {
            queryClient.invalidateQueries({ queryKey: ["myExpenses"] });
            queryClient.invalidateQueries({ queryKey: ["teamExpenses"] });
            setSelectedClaim(null);
          }}
        />
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {activeTab === "my" ? "My Claims" : "Team Claims"}
        </h3>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1 flex-wrap">
            {(["all", "pending", "approved", "rejected", "reimbursed"] as const).map(
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
                  {s === "all" ? "All" : (STATUS_CONFIG[s]?.label || s)}
                </button>
              ),
            )}
          </div>
        </div>
      </div>

      {/* Claims List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {(activeData?.data ?? []).map((claim) => (
              <ClaimCard
                key={claim.id}
                claim={claim}
                isSelected={selectedClaim?.id === claim.id}
                showEmployee={activeTab === "team"}
                onSelect={() =>
                  setSelectedClaim(
                    selectedClaim?.id === claim.id ? null : claim,
                  )
                }
              />
            ))}
            {(activeData?.data ?? []).length === 0 && (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-16">
                  <Receipt className="h-12 w-12 text-muted-foreground/40" />
                  <p className="mt-3 text-sm text-muted-foreground">
                    No expense claims found
                  </p>
                  {activeTab === "my" && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-4 gap-2"
                      onClick={() => setShowForm(true)}
                    >
                      <Plus className="h-4 w-4" /> Submit your first claim
                    </Button>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Pagination */}
          {activeData && (activeData?.meta?.total_pages ?? 0) > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!activeData?.meta?.has_prev}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {activeData?.meta?.page ?? 1} of {activeData?.meta?.total_pages ?? 1}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!activeData?.meta?.has_next}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Claim Card ─────────────────────────────────────────────────────

function ClaimCard({
  claim,
  isSelected,
  showEmployee,
  onSelect,
}: {
  claim: ExpenseClaim;
  isSelected: boolean;
  showEmployee: boolean;
  onSelect: () => void;
}) {
  const claimStatus = getClaimStatus(claim);
  const statusCfg = STATUS_CONFIG[claimStatus] || STATUS_CONFIG.pending;
  const StatusIcon = statusCfg.icon;

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary ring-offset-2",
      )}
      onClick={onSelect}
    >
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Left */}
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="mt-0.5 text-xl">💰</div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                {claim.claim_number && (
                  <span className="text-xs font-mono text-muted-foreground">
                    #{claim.claim_number}
                  </span>
                )}
              </div>
              <p className="mt-1 font-semibold text-foreground line-clamp-1">
                {claim.title}
              </p>
              {claim.remarks && (
                <p className="mt-0.5 text-sm text-muted-foreground line-clamp-1">
                  {claim.remarks}
                </p>
              )}
              <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                {claim.created_at && <span>{formatDate(claim.created_at)}</span>}
                {showEmployee && claim.employee_name && (
                  <>
                    <span>·</span>
                    <span>{claim.employee_name}</span>
                  </>
                )}
                {claim.currency && claim.currency !== "INR" && (
                  <>
                    <span>·</span>
                    <span>{claim.currency}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-4 sm:flex-col sm:items-end">
            <p className="text-lg font-bold tabular-nums text-foreground">
              {formatCurrency(claim.amount ?? 0)}
            </p>
            <Badge className={cn("gap-1 border text-xs", statusCfg.bg, statusCfg.text)}>
              <StatusIcon className="h-3 w-3" />
              {statusCfg.label}
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Create Expense Form ────────────────────────────────────────────

function CreateExpenseForm({ onSuccess }: { onSuccess: () => void }) {
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("");
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: expensesApi.createExpenseClaim,
    onSuccess: () => {
      setError(null);
      onSuccess();
    },
    onError: (err: any) => {
      setError(
        err?.response?.data?.detail || err?.message || "Failed to create claim",
      );
    },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      if (!title.trim()) {
        setError("Please enter a title");
        return;
      }
      const parsedAmount = parseFloat(amount);
      if (!amount || isNaN(parsedAmount) || parsedAmount <= 0) {
        setError("Please enter a valid amount");
        return;
      }

      createMut.mutate({
        title: title.trim(),
        amount: parsedAmount,
        remarks: remarks.trim() || undefined,
      });
    },
    [title, amount, remarks, createMut],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Receipt className="h-5 w-5 text-primary" />
          New Expense Claim
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            {/* Title */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g., Client meeting travel expenses"
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            {/* Amount */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                Amount (₹) <span className="text-red-500">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                  ₹
                </span>
                <input
                  type="number"
                  min="1"
                  step="0.01"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  placeholder="0"
                  className="flex h-9 w-full rounded-md border border-input bg-background pl-7 pr-3 py-1 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
              </div>
            </div>

            {/* Remarks */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">Remarks</label>
              <textarea
                value={remarks}
                onChange={(e) => setRemarks(e.target.value)}
                placeholder="Provide details about the expense..."
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              />
            </div>
          </div>

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
              disabled={createMut.isPending}
              className="gap-2 min-w-[160px]"
            >
              <Send className="h-4 w-4" />
              {createMut.isPending ? "Submitting…" : "Submit Claim"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Claim Detail View ──────────────────────────────────────────────

function ClaimDetailView({
  claim,
  isManager,
  onClose,
  onUpdate,
}: {
  claim: ExpenseClaim;
  isManager: boolean;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  const claimStatus = getClaimStatus(claim);
  const statusCfg = STATUS_CONFIG[claimStatus] || STATUS_CONFIG.pending;

  const approveMut = useMutation({
    mutationFn: () => expensesApi.approveExpense(claim.id),
    onSuccess: () => onUpdate(),
  });

  const rejectMut = useMutation({
    mutationFn: () => expensesApi.rejectExpense(claim.id, rejectReason),
    onSuccess: () => onUpdate(),
  });

  const canApprove = isManager && (claimStatus === "pending" || claimStatus === "submitted");

  return (
    <Card className="border-primary/20">
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            {claim.claim_number && (
              <span className="text-xs font-mono text-muted-foreground">
                #{claim.claim_number}
              </span>
            )}
            <Badge className={cn("border text-xs", statusCfg.bg, statusCfg.text)}>
              {statusCfg.label}
            </Badge>
          </div>
          <CardTitle className="text-lg">{claim.title}</CardTitle>
          {claim.remarks && (
            <CardDescription className="mt-2">{claim.remarks}</CardDescription>
          )}
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            {claim.created_at && <span>Submitted {formatDate(claim.created_at)}</span>}
            {claim.employee_name && (
              <>
                <span>·</span>
                <span>By {claim.employee_name}</span>
              </>
            )}
            {claim.approved_at && (
              <>
                <span>·</span>
                <span>Reviewed {formatDate(claim.approved_at)}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-start gap-3">
          <div className="text-right">
            <p className="text-2xl font-bold tabular-nums text-foreground">
              {formatCurrency(claim.amount ?? 0)}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Manager approval actions */}
        {canApprove && (
          <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3">
            <p className="text-sm font-medium text-blue-700">Approval Actions</p>
            <div className="flex items-center gap-3">
              <Button
                size="sm"
                className="gap-1.5 bg-emerald-600 hover:bg-emerald-700"
                onClick={() => approveMut.mutate()}
                disabled={approveMut.isPending || rejectMut.isPending}
              >
                {approveMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                Approve
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5 border-red-200 text-red-700 hover:bg-red-50"
                onClick={() => setShowReject(!showReject)}
                disabled={approveMut.isPending || rejectMut.isPending}
              >
                <Ban className="h-3.5 w-3.5" />
                Reject
              </Button>
            </div>

            {showReject && (
              <div className="space-y-2">
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Reason for rejection..."
                  rows={2}
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                />
                <Button
                  variant="destructive"
                  size="sm"
                  className="gap-1.5"
                  onClick={() => rejectMut.mutate()}
                  disabled={!rejectReason.trim() || rejectMut.isPending}
                >
                  {rejectMut.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" />
                  )}
                  Confirm Reject
                </Button>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
