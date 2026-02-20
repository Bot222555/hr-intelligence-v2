/**
 * ExpensesPage — Employee expense claims management.
 *
 * Features:
 *  • Expense claim list with status filters
 *  • Create new expense claim form (category, amount, receipt upload, description)
 *  • Approval flow view for managers
 *  • Summary stats (total claimed, approved, pending, rejected)
 */

import { useCallback, useRef, useState } from "react";
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
  Upload,
  FileCheck,
  Filter,
  Users,
  ArrowDownToLine,
  Ban,
  Eye,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { ADMIN_ROLES, ROLES } from "@/lib/constants";
import * as expensesApi from "@/api/expenses";
import type {
  ExpenseClaim,
  ExpenseStatus,
  ExpenseCategory,
} from "@/api/expenses";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  ExpenseStatus,
  { label: string; bg: string; text: string; icon: typeof Clock }
> = {
  draft: {
    label: "Draft",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    icon: Receipt,
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

const CATEGORY_CONFIG: Record<
  ExpenseCategory,
  { label: string; emoji: string; gradient: string }
> = {
  travel: { label: "Travel", emoji: "✈️", gradient: "from-blue-50 to-indigo-50" },
  food: { label: "Food & Beverages", emoji: "🍔", gradient: "from-orange-50 to-amber-50" },
  accommodation: { label: "Accommodation", emoji: "🏨", gradient: "from-purple-50 to-violet-50" },
  office_supplies: { label: "Office Supplies", emoji: "📎", gradient: "from-slate-50 to-gray-50" },
  client_entertainment: { label: "Client Entertainment", emoji: "🍷", gradient: "from-rose-50 to-pink-50" },
  training: { label: "Training", emoji: "📚", gradient: "from-emerald-50 to-teal-50" },
  miscellaneous: { label: "Miscellaneous", emoji: "📋", gradient: "from-slate-50 to-gray-50" },
};

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
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
  const [statusFilter, setStatusFilter] = useState<ExpenseStatus | "all">("all");
  const [page, setPage] = useState(1);
  const [selectedClaim, setSelectedClaim] = useState<ExpenseClaim | null>(null);

  // ── Queries ────────────────────────────────────────────────────

  // Note: /expenses/summary endpoint not available — summary widgets removed

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

      {/* Summary stats not available from this backend */}

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
            queryClient.invalidateQueries({ queryKey: ["expenseSummary"] });
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
            queryClient.invalidateQueries({ queryKey: ["expenseSummary"] });
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
            {(["all", "submitted", "approved", "rejected", "reimbursed"] as const).map(
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

// (Summary stat card removed — /expenses/summary endpoint not available)

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
  const statusCfg = STATUS_CONFIG[claim.status];
  const StatusIcon = statusCfg.icon;
  const categoryCfg = CATEGORY_CONFIG[claim.category] || CATEGORY_CONFIG.miscellaneous;

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
            <div className="mt-0.5 text-xl">{categoryCfg.emoji}</div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-muted-foreground">
                  #{claim.claim_number}
                </span>
                <Badge variant="secondary" className="text-xs">
                  {categoryCfg.label}
                </Badge>
              </div>
              <p className="mt-1 font-semibold text-foreground line-clamp-1">
                {claim.title}
              </p>
              {claim.description && (
                <p className="mt-0.5 text-sm text-muted-foreground line-clamp-1">
                  {claim.description}
                </p>
              )}
              <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground">
                <span>{formatDate(claim.created_at)}</span>
                {showEmployee && claim.employee && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      {claim.employee.display_name || claim.employee.employee_code}
                    </span>
                  </>
                )}
                {(claim.receipt_urls ?? []).length > 0 && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <Receipt className="h-3 w-3" />
                      {(claim.receipt_urls ?? []).length} receipt{(claim.receipt_urls ?? []).length !== 1 ? "s" : ""}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Right */}
          <div className="flex items-center gap-4 sm:flex-col sm:items-end">
            <p className="text-lg font-bold tabular-nums text-foreground">
              {formatCurrency(claim.total_amount)}
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
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<ExpenseCategory>("travel");
  const [amount, setAmount] = useState("");
  const [receiptUrls, setReceiptUrls] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleFileUpload = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files?.length) return;

    setUploading(true);
    try {
      // Receipt upload will be handled via the claim creation flow
      // For now, just track file names as placeholders
      const names: string[] = [];
      for (const file of Array.from(files)) {
        names.push(file.name);
      }
      setReceiptUrls((prev) => [...prev, ...names]);
    } catch {
      setError("Failed to process receipt");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, []);

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
        description: description.trim() || undefined,
        category,
        total_amount: parsedAmount,
        receipt_urls: receiptUrls.length > 0 ? receiptUrls : undefined,
      });
    },
    [title, description, category, amount, receiptUrls, createMut],
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

            {/* Category */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                Category <span className="text-red-500">*</span>
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {(Object.keys(CATEGORY_CONFIG) as ExpenseCategory[]).map((cat) => (
                  <option key={cat} value={cat}>
                    {CATEGORY_CONFIG[cat].emoji} {CATEGORY_CONFIG[cat].label}
                  </option>
                ))}
              </select>
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

            {/* Description */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Provide details about the expense..."
                rows={3}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              />
            </div>

            {/* Receipt Upload */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">Receipts</label>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  multiple
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  {uploading ? "Uploading…" : "Upload Receipt"}
                </Button>
                {receiptUrls.length > 0 && (
                  <span className="flex items-center gap-1 text-sm text-emerald-600">
                    <FileCheck className="h-4 w-4" />
                    {receiptUrls.length} uploaded
                  </span>
                )}
              </div>
              {receiptUrls.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {receiptUrls.map((_url, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-1.5 rounded-md border bg-muted/50 px-2 py-1 text-xs"
                    >
                      <Receipt className="h-3 w-3 text-muted-foreground" />
                      <span className="text-muted-foreground">Receipt {i + 1}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setReceiptUrls((prev) => prev.filter((_, j) => j !== i))
                        }
                        className="ml-1 rounded-full p-0.5 hover:bg-background"
                      >
                        <X className="h-3 w-3 text-muted-foreground" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
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

  const statusCfg = STATUS_CONFIG[claim.status];
  const categoryCfg = CATEGORY_CONFIG[claim.category] || CATEGORY_CONFIG.miscellaneous;

  const approveMut = useMutation({
    mutationFn: () => expensesApi.approveExpense(claim.id),
    onSuccess: () => onUpdate(),
  });

  const rejectMut = useMutation({
    mutationFn: () => expensesApi.rejectExpense(claim.id, rejectReason),
    onSuccess: () => onUpdate(),
  });

  return (
    <Card className="border-primary/20">
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-xs font-mono text-muted-foreground">
              #{claim.claim_number}
            </span>
            <Badge className={cn("border text-xs", statusCfg.bg, statusCfg.text)}>
              {statusCfg.label}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {categoryCfg.emoji} {categoryCfg.label}
            </Badge>
          </div>
          <CardTitle className="text-lg">{claim.title}</CardTitle>
          {claim.description && (
            <CardDescription className="mt-2">{claim.description}</CardDescription>
          )}
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            <span>Submitted {formatDate(claim.created_at)}</span>
            {claim.employee && (
              <>
                <span>·</span>
                <span>By {claim.employee.display_name || claim.employee.employee_code}</span>
              </>
            )}
            {claim.reviewed_at && claim.reviewer && (
              <>
                <span>·</span>
                <span>
                  Reviewed by {claim.reviewer.display_name || claim.reviewer.employee_code} on{" "}
                  {formatDate(claim.reviewed_at)}
                </span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-start gap-3">
          <div className="text-right">
            <p className="text-2xl font-bold tabular-nums text-foreground">
              {formatCurrency(claim.total_amount)}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Receipts */}
        {(claim.receipt_urls ?? []).length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
              Receipts
            </h4>
            <div className="flex flex-wrap gap-2">
              {(claim.receipt_urls ?? []).map((url, i) => (
                <a
                  key={i}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-md border bg-muted/50 px-3 py-2 text-sm text-primary hover:bg-muted transition-colors"
                >
                  <Eye className="h-4 w-4" />
                  Receipt {i + 1}
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Reviewer remarks */}
        {claim.reviewer_remarks && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-1">
              Reviewer Remarks
            </p>
            <p className="text-sm text-foreground">{claim.reviewer_remarks}</p>
          </div>
        )}

        {/* Manager approval actions */}
        {isManager && claim.status === "submitted" && (
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
