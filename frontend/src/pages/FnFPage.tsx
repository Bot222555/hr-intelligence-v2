/**
 * FnFPage — Full & Final Settlement management.
 *
 * Features:
 *  • List all FnF records with filters
 *  • Summary stats (pending, completed, total amount)
 *  • Detail view with settlement components
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Loader2,
  Clock,
  CheckCircle2,
  IndianRupee,
  Filter,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import * as fnfApi from "@/api/fnf";
import type { FnFRecord } from "@/api/fnf";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; bg: string; text: string; icon: typeof Clock }> = {
  pending: {
    label: "Pending",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
    icon: Clock,
  },
  in_progress: {
    label: "In Progress",
    bg: "bg-blue-50 border-blue-200",
    text: "text-blue-700",
    icon: Clock,
  },
  completed: {
    label: "Completed",
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
    icon: CheckCircle2,
  },
};

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

// ── Component ──────────────────────────────────────────────────────

export function FnFPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedRecord, setSelectedRecord] = useState<FnFRecord | null>(null);
  const [page, setPage] = useState(1);

  const { data: fnfData, isLoading } = useQuery({
    queryKey: ["fnfList", statusFilter, page],
    queryFn: () =>
      fnfApi.getFnFList({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 10,
      }),
  });

  const { data: summaryData } = useQuery({
    queryKey: ["fnfSummary"],
    queryFn: () => fnfApi.getFnFSummary(),
  });

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Full & Final Settlement</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage employee separation and settlement records
        </p>
      </div>

      {/* Summary cards */}
      {summaryData && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card className="border-0 bg-gradient-to-br from-amber-50 to-orange-50 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <div className="rounded-xl bg-amber-100 p-3">
                <Clock className="h-5 w-5 text-amber-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Pending</p>
                <p className="text-2xl font-bold text-foreground">{summaryData.total_pending ?? 0}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 bg-gradient-to-br from-emerald-50 to-teal-50 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <div className="rounded-xl bg-emerald-100 p-3">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Completed</p>
                <p className="text-2xl font-bold text-foreground">{summaryData.total_completed ?? 0}</p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 bg-gradient-to-br from-blue-50 to-indigo-50 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <div className="rounded-xl bg-blue-100 p-3">
                <IndianRupee className="h-5 w-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Pending Amount</p>
                <p className="text-2xl font-bold text-foreground">
                  {formatCurrency(summaryData.total_amount_pending ?? 0)}
                </p>
              </div>
            </CardContent>
          </Card>
          <Card className="border-0 bg-gradient-to-br from-violet-50 to-purple-50 shadow-sm">
            <CardContent className="flex items-center gap-4 p-5">
              <div className="rounded-xl bg-violet-100 p-3">
                <IndianRupee className="h-5 w-5 text-violet-600" />
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Settled Amount</p>
                <p className="text-2xl font-bold text-foreground">
                  {formatCurrency(summaryData.total_amount_settled ?? 0)}
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Settlements
        </h3>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1">
            {(["all", "pending", "in_progress", "completed"] as const).map((s) => (
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
            ))}
          </div>
        </div>
      </div>

      {/* Detail view */}
      {selectedRecord && (
        <FnFDetailView record={selectedRecord} onClose={() => setSelectedRecord(null)} />
      )}

      {/* List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {(fnfData?.data ?? []).map((record) => (
              <FnFCard
                key={record.id}
                record={record}
                isSelected={selectedRecord?.id === record.id}
                onSelect={() => setSelectedRecord(selectedRecord?.id === record.id ? null : record)}
              />
            ))}
            {(fnfData?.data ?? []).length === 0 && (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-16">
                  <FileText className="h-12 w-12 text-muted-foreground/40" />
                  <p className="mt-3 text-sm text-muted-foreground">
                    No settlement records found
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── FnF Card ───────────────────────────────────────────────────────

function FnFCard({
  record,
  isSelected,
  onSelect,
}: {
  record: FnFRecord;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const statusCfg = STATUS_CONFIG[record.status] || STATUS_CONFIG.pending;
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
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="mt-0.5 text-xl">📋</div>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-foreground">
                {record.employee_name || record.employee_code || "Employee"}
              </p>
              <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
                {record.last_working_date && <span>LWD: {record.last_working_date}</span>}
                {record.resignation_date && (
                  <>
                    <span>·</span>
                    <span>Resigned: {record.resignation_date}</span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4 sm:flex-col sm:items-end">
            <p className="text-lg font-bold tabular-nums text-foreground">
              {formatCurrency(record.net_settlement ?? 0)}
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

// ── FnF Detail View ────────────────────────────────────────────────

function FnFDetailView({
  record,
  onClose,
}: {
  record: FnFRecord;
  onClose: () => void;
}) {
  const statusCfg = STATUS_CONFIG[record.status] || STATUS_CONFIG.pending;
  const payable = (record.components ?? []).filter((c) => c.type === "payable");
  const recoverable = (record.components ?? []).filter((c) => c.type === "recoverable");

  return (
    <Card className="border-primary/20">
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Badge className={cn("border text-xs", statusCfg.bg, statusCfg.text)}>
              {statusCfg.label}
            </Badge>
          </div>
          <CardTitle className="text-lg">
            {record.employee_name || record.employee_code || "Employee"} — F&F Settlement
          </CardTitle>
          <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            {record.last_working_date && <span>LWD: {record.last_working_date}</span>}
            {record.created_at && (
              <>
                <span>·</span>
                <span>Created {formatDate(record.created_at)}</span>
              </>
            )}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          ✕
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="rounded-xl bg-emerald-50 p-4 text-center">
            <p className="text-xs font-medium uppercase text-muted-foreground">Total Payable</p>
            <p className="mt-1 text-2xl font-bold text-emerald-700">
              {formatCurrency(record.total_payable ?? 0)}
            </p>
          </div>
          <div className="rounded-xl bg-red-50 p-4 text-center">
            <p className="text-xs font-medium uppercase text-muted-foreground">Total Recoverable</p>
            <p className="mt-1 text-2xl font-bold text-red-700">
              {formatCurrency(record.total_recoverable ?? 0)}
            </p>
          </div>
          <div className="rounded-xl bg-primary/10 p-4 text-center">
            <p className="text-xs font-medium uppercase text-muted-foreground">Net Settlement</p>
            <p className="mt-1 text-2xl font-bold text-primary">
              {formatCurrency(record.net_settlement ?? 0)}
            </p>
          </div>
        </div>

        {(payable.length > 0 || recoverable.length > 0) && (
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            {payable.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-emerald-600">
                  Payable Components
                </h4>
                <div className="space-y-1">
                  {payable.map((c, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-muted-foreground">{c.name}</span>
                      <span className="font-medium tabular-nums">{formatCurrency(c.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {recoverable.length > 0 && (
              <div>
                <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-red-600">
                  Recoverable Components
                </h4>
                <div className="space-y-1">
                  {recoverable.map((c, i) => (
                    <div key={i} className="flex justify-between text-sm">
                      <span className="text-muted-foreground">{c.name}</span>
                      <span className="font-medium tabular-nums text-red-600">
                        -{formatCurrency(c.amount)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
