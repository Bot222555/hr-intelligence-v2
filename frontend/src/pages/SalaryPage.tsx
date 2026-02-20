/**
 * SalaryPage — Employee salary self-service.
 *
 * Features:
 *  • Monthly salary slip view (current + history)
 *  • CTC breakdown chart (recharts PieChart)
 *  • Salary components table
 *  • Download salary slip as PDF button
 *  • Team salary view for managers
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  Legend,
} from "recharts";
import {
  Banknote,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  IndianRupee,
  FileText,
  Loader2,
  CheckCircle2,
  Clock,
  XCircle,
  ArrowUpRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn, formatDate } from "@/lib/utils";
import * as salaryApi from "@/api/salary";
import type { SalarySlip, SalaryComponent } from "@/api/salary";

// ── Helpers ────────────────────────────────────────────────────────

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const PAYMENT_STATUS_CONFIG: Record<
  string,
  { label: string; bg: string; text: string; icon: typeof Clock }
> = {
  pending: { label: "Pending", bg: "bg-amber-50 border-amber-200", text: "text-amber-700", icon: Clock },
  processed: { label: "Processed", bg: "bg-blue-50 border-blue-200", text: "text-blue-700", icon: ArrowUpRight },
  paid: { label: "Paid", bg: "bg-emerald-50 border-emerald-200", text: "text-emerald-700", icon: CheckCircle2 },
  failed: { label: "Failed", bg: "bg-red-50 border-red-200", text: "text-red-700", icon: XCircle },
};

const PIE_COLORS = [
  "#6C5CE7", "#00B894", "#0984E3", "#FDCB6E", "#E17055",
  "#00CEC9", "#A29BFE", "#55A3F5", "#FF7675", "#74B9FF",
];

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount);
}

// ── Component ──────────────────────────────────────────────────────

export function SalaryPage() {
  const [activeTab, setActiveTab] = useState<"slips" | "ctc">("slips");
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [selectedSlip, setSelectedSlip] = useState<SalarySlip | null>(null);

  // ── Queries ────────────────────────────────────────────────────

  const { data: slipsData, isLoading: loadingSlips } = useQuery({
    queryKey: ["salarySlips", selectedYear],
    queryFn: () => salaryApi.getMySalarySlips({ year: selectedYear }),
  });

  const { data: ctcData, isLoading: loadingCtc } = useQuery({
    queryKey: ["ctcBreakdown"],
    queryFn: () => salaryApi.getCTCBreakdown(),
    enabled: activeTab === "ctc",
    retry: 1,
  });

  // ── CTC Chart Data ───────────────────────────────────────────────

  const ctcChartData = useMemo(() => {
    if (!ctcData?.components) return [];
    return (ctcData.components ?? [])
      .filter((c) => c.type === "earning")
      .map((c) => ({
        name: c.name,
        value: c.monthly_amount ?? 0,
        percentage: c.percentage_of_ctc ?? 0,
      }));
  }, [ctcData]);

  // deduction data is shown in the CTC table below, not in a separate chart

  // ── Render ───────────────────────────────────────────────────────

  const tabs = [
    { key: "slips" as const, label: "Salary Slips", icon: FileText },
    { key: "ctc" as const, label: "CTC Breakdown", icon: TrendingUp },
  ];

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">Salary</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          View your salary slips, CTC breakdown, and payment history
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex items-center gap-1 rounded-lg bg-muted p-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all",
                activeTab === tab.key
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* ── Salary Slips Tab ────────────────────────────────────── */}
      {activeTab === "slips" && (
        <div className="space-y-6">
          {/* Year selector */}
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="icon"
              onClick={() => setSelectedYear((y) => y - 1)}
              className="h-8 w-8"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-[80px] text-center text-sm font-semibold">
              {selectedYear}
            </span>
            <Button
              variant="outline"
              size="icon"
              onClick={() => setSelectedYear((y) => y + 1)}
              disabled={selectedYear >= new Date().getFullYear()}
              className="h-8 w-8"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>

          {/* Selected slip detail */}
          {selectedSlip && (
            <SlipDetailCard
              slip={selectedSlip}
              onClose={() => setSelectedSlip(null)}
            />
          )}

          {/* Slips grid */}
          {loadingSlips ? (
            <LoadingPlaceholder />
          ) : !(slipsData?.data ?? []).length ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16">
                <Banknote className="h-12 w-12 text-muted-foreground/40" />
                <p className="mt-3 text-sm text-muted-foreground">
                  No salary slips found for {selectedYear}
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(slipsData?.data ?? []).map((slip) => (
                <SlipCard
                  key={slip.id}
                  slip={slip}
                  isSelected={selectedSlip?.id === slip.id}
                  onSelect={() =>
                    setSelectedSlip(
                      selectedSlip?.id === slip.id ? null : slip,
                    )
                  }
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── CTC Breakdown Tab ───────────────────────────────────── */}
      {activeTab === "ctc" && (
        <div className="space-y-6">
          {loadingCtc ? (
            <LoadingPlaceholder />
          ) : !ctcData ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16">
                <TrendingUp className="h-12 w-12 text-muted-foreground/40" />
                <p className="mt-3 text-sm text-muted-foreground">
                  CTC breakdown not available
                </p>
              </CardContent>
            </Card>
          ) : (
            <>
              {/* CTC summary cards */}
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <Card className="border-0 bg-gradient-to-br from-violet-50 to-purple-50 shadow-sm">
                  <CardContent className="flex items-center gap-4 p-5">
                    <div className="rounded-xl bg-violet-100 p-3">
                      <IndianRupee className="h-5 w-5 text-violet-600" />
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Annual CTC</p>
                      <p className="text-2xl font-bold text-foreground">
                        {formatCurrency(ctcData?.annual_ctc ?? 0)}
                      </p>
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-0 bg-gradient-to-br from-emerald-50 to-teal-50 shadow-sm">
                  <CardContent className="flex items-center gap-4 p-5">
                    <div className="rounded-xl bg-emerald-100 p-3">
                      <Banknote className="h-5 w-5 text-emerald-600" />
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Monthly CTC</p>
                      <p className="text-2xl font-bold text-foreground">
                        {formatCurrency(ctcData?.monthly_ctc ?? 0)}
                      </p>
                    </div>
                  </CardContent>
                </Card>
                <Card className="border-0 bg-gradient-to-br from-blue-50 to-indigo-50 shadow-sm">
                  <CardContent className="flex items-center gap-4 p-5">
                    <div className="rounded-xl bg-blue-100 p-3">
                      <TrendingUp className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                      <p className="text-sm text-muted-foreground">Components</p>
                      <p className="text-2xl font-bold text-foreground">
                        {(ctcData?.components ?? []).length}
                      </p>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Charts */}
              <div className="grid gap-6 lg:grid-cols-2">
                {/* Pie chart - Earnings */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Earnings Breakdown</CardTitle>
                    <CardDescription>Monthly earning components</CardDescription>
                  </CardHeader>
                  <CardContent>
                    {ctcChartData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                          <Pie
                            data={ctcChartData}
                            cx="50%"
                            cy="50%"
                            innerRadius={70}
                            outerRadius={110}
                            paddingAngle={3}
                            dataKey="value"
                            nameKey="name"
                          >
                            {ctcChartData.map((_, i) => (
                              <Cell
                                key={i}
                                fill={PIE_COLORS[i % PIE_COLORS.length]}
                              />
                            ))}
                          </Pie>
                          <RechartsTooltip
                            formatter={(value: number | undefined) => formatCurrency(value ?? 0)}
                            contentStyle={{
                              borderRadius: "8px",
                              border: "1px solid #e2e8f0",
                              fontSize: "13px",
                            }}
                          />
                          <Legend
                            iconType="circle"
                            iconSize={8}
                            wrapperStyle={{ fontSize: "12px" }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <div className="flex h-[300px] items-center justify-center">
                        <p className="text-sm text-muted-foreground">No data</p>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* Components table */}
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">All Components</CardTitle>
                    <CardDescription>Earnings, deductions & employer contributions</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="max-h-[320px] overflow-y-auto">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-background">
                          <tr className="border-b text-left">
                            <th className="pb-2 font-medium text-muted-foreground">Component</th>
                            <th className="pb-2 text-right font-medium text-muted-foreground">Monthly</th>
                            <th className="pb-2 text-right font-medium text-muted-foreground">Annual</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y">
                          {/* Earnings */}
                          <tr>
                            <td colSpan={3} className="pt-3 pb-1">
                              <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600">
                                Earnings
                              </span>
                            </td>
                          </tr>
                          {(ctcData?.components ?? [])
                            .filter((c) => c.type === "earning")
                            .map((c) => (
                              <tr key={c.name} className="group">
                                <td className="py-2 text-foreground">{c.name}</td>
                                <td className="py-2 text-right font-medium tabular-nums text-foreground">
                                  {formatCurrency(c.monthly_amount ?? 0)}
                                </td>
                                <td className="py-2 text-right tabular-nums text-muted-foreground">
                                  {formatCurrency(c.annual_amount ?? 0)}
                                </td>
                              </tr>
                            ))}

                          {/* Deductions */}
                          <tr>
                            <td colSpan={3} className="pt-4 pb-1">
                              <span className="text-xs font-semibold uppercase tracking-wider text-red-600">
                                Deductions
                              </span>
                            </td>
                          </tr>
                          {(ctcData?.components ?? [])
                            .filter((c) => c.type === "deduction")
                            .map((c) => (
                              <tr key={c.name} className="group">
                                <td className="py-2 text-foreground">{c.name}</td>
                                <td className="py-2 text-right font-medium tabular-nums text-red-600">
                                  -{formatCurrency(c.monthly_amount ?? 0)}
                                </td>
                                <td className="py-2 text-right tabular-nums text-muted-foreground">
                                  -{formatCurrency(c.annual_amount ?? 0)}
                                </td>
                              </tr>
                            ))}

                          {/* Employer Contributions */}
                          {(ctcData?.components ?? []).some((c) => c.type === "employer_contribution") && (
                            <>
                              <tr>
                                <td colSpan={3} className="pt-4 pb-1">
                                  <span className="text-xs font-semibold uppercase tracking-wider text-blue-600">
                                    Employer Contributions
                                  </span>
                                </td>
                              </tr>
                              {(ctcData?.components ?? [])
                                .filter((c) => c.type === "employer_contribution")
                                .map((c) => (
                                  <tr key={c.name} className="group">
                                    <td className="py-2 text-foreground">{c.name}</td>
                                    <td className="py-2 text-right font-medium tabular-nums text-blue-600">
                                      {formatCurrency(c.monthly_amount ?? 0)}
                                    </td>
                                    <td className="py-2 text-right tabular-nums text-muted-foreground">
                                      {formatCurrency(c.annual_amount ?? 0)}
                                    </td>
                                  </tr>
                                ))}
                            </>
                          )}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>
      )}

    </div>
  );
}

// ── Slip Card ──────────────────────────────────────────────────────

function SlipCard({
  slip,
  isSelected,
  onSelect,
}: {
  slip: SalarySlip;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const statusCfg = PAYMENT_STATUS_CONFIG[slip.payment_status] || PAYMENT_STATUS_CONFIG.pending;
  const StatusIcon = statusCfg.icon;

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary ring-offset-2",
      )}
      onClick={onSelect}
    >
      <CardContent className="p-5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              {MONTH_NAMES[(slip.month ?? 1) - 1]} {slip.year ?? ""}
            </p>
            <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
              {formatCurrency(slip.net_salary ?? 0)}
            </p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Gross: {formatCurrency(slip.gross_earnings ?? 0)}
            </p>
          </div>
          <Badge className={cn("gap-1 border text-xs", statusCfg.bg, statusCfg.text)}>
            <StatusIcon className="h-3 w-3" />
            {statusCfg.label}
          </Badge>
        </div>

        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {slip.days_worked ?? 0}/{slip.days_payable ?? 0} days
            {(slip.loss_of_pay_days ?? 0) > 0 && (
              <span className="ml-1 text-red-500">
                ({slip.loss_of_pay_days} LOP)
              </span>
            )}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Slip Detail Card ───────────────────────────────────────────────

function SlipDetailCard({
  slip,
  onClose,
}: {
  slip: SalarySlip;
  onClose: () => void;
}) {
  const earnings = (slip.components ?? []).filter((c) => c.type === "earning");
  const deductions = (slip.components ?? []).filter((c) => c.type === "deduction");
  const employer = (slip.components ?? []).filter((c) => c.type === "employer_contribution");

  return (
    <Card className="border-primary/20 bg-gradient-to-br from-slate-50 to-gray-50">
      <CardHeader className="flex-row items-center justify-between pb-2">
        <div>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            {MONTH_NAMES[(slip.month ?? 1) - 1]} {slip.year ?? ""} — Salary Slip
          </CardTitle>
          <CardDescription>
            Payment date: {slip.payment_date ? formatDate(slip.payment_date) : "Pending"}
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            ✕
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Earnings */}
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-emerald-600">
              <TrendingUp className="h-4 w-4" />
              Earnings
            </h4>
            <div className="space-y-2">
              {earnings.map((c) => (
                <ComponentRow key={c.name} component={c} />
              ))}
              <div className="mt-2 border-t pt-2">
                <div className="flex justify-between text-sm font-bold text-foreground">
                  <span>Gross Earnings</span>
                  <span className="tabular-nums">{formatCurrency(slip.gross_earnings)}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Deductions */}
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-red-600">
              <TrendingDown className="h-4 w-4" />
              Deductions
            </h4>
            <div className="space-y-2">
              {deductions.map((c) => (
                <ComponentRow key={c.name} component={c} negative />
              ))}
              <div className="mt-2 border-t pt-2">
                <div className="flex justify-between text-sm font-bold text-foreground">
                  <span>Total Deductions</span>
                  <span className="tabular-nums text-red-600">
                    -{formatCurrency(slip.total_deductions)}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Net Pay */}
          <div>
            <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-primary">
              <IndianRupee className="h-4 w-4" />
              Summary
            </h4>
            <div className="space-y-3">
              <div className="rounded-xl bg-primary/10 p-4 text-center">
                <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Net Salary
                </p>
                <p className="mt-1 text-3xl font-bold tabular-nums text-primary">
                  {formatCurrency(slip.net_salary)}
                </p>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Days Worked</span>
                  <span className="font-medium text-foreground">
                    {slip.days_worked}/{slip.days_payable}
                  </span>
                </div>
                {slip.loss_of_pay_days > 0 && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">LOP Days</span>
                    <span className="font-medium text-red-600">
                      {slip.loss_of_pay_days}
                    </span>
                  </div>
                )}
                {employer.length > 0 && (
                  <>
                    <div className="my-1 h-px bg-border" />
                    <p className="text-xs font-semibold uppercase tracking-wider text-blue-600">
                      Employer Contributions
                    </p>
                    {employer.map((c) => (
                      <div key={c.name} className="flex justify-between">
                        <span className="text-muted-foreground">{c.name}</span>
                        <span className="font-medium tabular-nums text-blue-600">
                          {formatCurrency(c.amount)}
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Component Row ──────────────────────────────────────────────────

function ComponentRow({
  component,
  negative,
}: {
  component: SalaryComponent;
  negative?: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-md px-2 py-1 transition-colors hover:bg-background">
      <span className="text-sm text-muted-foreground">{component.name}</span>
      <span
        className={cn(
          "text-sm font-medium tabular-nums",
          negative ? "text-red-600" : "text-foreground",
        )}
      >
        {negative && "-"}
        {formatCurrency(component.amount)}
      </span>
    </div>
  );
}

// ── Loading ────────────────────────────────────────────────────────

function LoadingPlaceholder() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    </div>
  );
}
