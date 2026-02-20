/**
 * Admin Settings Page — Leave policies, shift policies.
 * Only visible to system_admin and hr_admin roles.
 */

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Settings,
  Plus,
  Edit3,
  Check,
  X,
  Clock,
  TreePalm,
  Sun,
  Moon,
  Shield,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import * as adminApi from "@/api/admin";
import type { LeaveType, ShiftPolicy } from "@/api/admin";

// ── Leave Type Form ────────────────────────────────────────────────

function LeaveTypeForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<LeaveType>;
  onSave: (data: Partial<LeaveType> & { code?: string; name: string }) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    code: initial?.code || "",
    name: initial?.name || "",
    description: initial?.description || "",
    default_balance: initial?.default_balance ?? 0,
    max_carry_forward: initial?.max_carry_forward ?? 0,
    is_paid: initial?.is_paid ?? true,
    requires_approval: initial?.requires_approval ?? true,
    min_days_notice: initial?.min_days_notice ?? 0,
    max_consecutive_days: initial?.max_consecutive_days ?? null,
  });

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {!initial?.id && (
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Code</label>
            <input
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })}
              placeholder="e.g. CL, EL, SL"
              maxLength={10}
            />
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Name</label>
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Casual Leave"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Description</label>
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Optional description"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Default Balance</label>
          <input
            type="number"
            step="0.5"
            min="0"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.default_balance}
            onChange={(e) => setForm({ ...form, default_balance: parseFloat(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Max Carry Forward</label>
          <input
            type="number"
            step="0.5"
            min="0"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.max_carry_forward}
            onChange={(e) => setForm({ ...form, max_carry_forward: parseFloat(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Min Days Notice</label>
          <input
            type="number"
            min="0"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.min_days_notice}
            onChange={(e) => setForm({ ...form, min_days_notice: parseInt(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Max Consecutive Days</label>
          <input
            type="number"
            min="1"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.max_consecutive_days ?? ""}
            onChange={(e) =>
              setForm({
                ...form,
                max_consecutive_days: e.target.value ? parseInt(e.target.value) : null,
              })
            }
            placeholder="No limit"
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_paid}
            onChange={(e) => setForm({ ...form, is_paid: e.target.checked })}
            className="rounded border-input"
          />
          Paid Leave
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.requires_approval}
            onChange={(e) => setForm({ ...form, requires_approval: e.target.checked })}
            className="rounded border-input"
          />
          Requires Approval
        </label>
      </div>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onSave(form)}>
          <Check className="mr-1 h-4 w-4" /> Save
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>
          <X className="mr-1 h-4 w-4" /> Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Shift Policy Form ──────────────────────────────────────────────

function ShiftForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: Partial<ShiftPolicy>;
  onSave: (data: Partial<ShiftPolicy> & { name: string }) => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState({
    name: initial?.name || "",
    start_time: initial?.start_time || "09:00",
    end_time: initial?.end_time || "18:00",
    grace_minutes: initial?.grace_minutes ?? 15,
    half_day_minutes: initial?.half_day_minutes ?? 240,
    full_day_minutes: initial?.full_day_minutes ?? 480,
    is_night_shift: initial?.is_night_shift ?? false,
  });

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Shift Name</label>
          <input
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="General Shift"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Start Time</label>
          <input
            type="time"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.start_time}
            onChange={(e) => setForm({ ...form, start_time: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">End Time</label>
          <input
            type="time"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.end_time}
            onChange={(e) => setForm({ ...form, end_time: e.target.value })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Grace Period (min)</label>
          <input
            type="number"
            min="0"
            max="120"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.grace_minutes}
            onChange={(e) => setForm({ ...form, grace_minutes: parseInt(e.target.value) || 0 })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Half Day (min)</label>
          <input
            type="number"
            min="60"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.half_day_minutes}
            onChange={(e) => setForm({ ...form, half_day_minutes: parseInt(e.target.value) || 240 })}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">Full Day (min)</label>
          <input
            type="number"
            min="120"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            value={form.full_day_minutes}
            onChange={(e) => setForm({ ...form, full_day_minutes: parseInt(e.target.value) || 480 })}
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={form.is_night_shift}
          onChange={(e) => setForm({ ...form, is_night_shift: e.target.checked })}
          className="rounded border-input"
        />
        Night Shift
      </label>
      <div className="flex gap-2">
        <Button size="sm" onClick={() => onSave(form)}>
          <Check className="mr-1 h-4 w-4" /> Save
        </Button>
        <Button size="sm" variant="outline" onClick={onCancel}>
          <X className="mr-1 h-4 w-4" /> Cancel
        </Button>
      </div>
    </div>
  );
}

// ── Main Settings Page ─────────────────────────────────────────────

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"leave" | "shifts">("leave");

  // ── Leave Types ──────────────────────────────────────────────────
  const [showLeaveForm, setShowLeaveForm] = useState(false);
  const [editingLeaveType, setEditingLeaveType] = useState<LeaveType | null>(null);

  const { data: leaveTypes = [], isLoading: ltLoading } = useQuery({
    queryKey: ["admin", "leave-types"],
    queryFn: adminApi.getLeaveTypes,
  });

  const createLT = useMutation({
    mutationFn: (data: adminApi.LeaveTypeCreate) => adminApi.createLeaveType(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "leave-types"] });
      setShowLeaveForm(false);
    },
  });

  const updateLT = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<LeaveType> }) =>
      adminApi.updateLeaveType(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "leave-types"] });
      setEditingLeaveType(null);
    },
  });

  // ── Shift Policies ───────────────────────────────────────────────
  const [showShiftForm, setShowShiftForm] = useState(false);
  const [editingShift, setEditingShift] = useState<ShiftPolicy | null>(null);

  const { data: shifts = [], isLoading: spLoading } = useQuery({
    queryKey: ["admin", "shift-policies"],
    queryFn: adminApi.getShiftPolicies,
  });

  const createSP = useMutation({
    mutationFn: (data: adminApi.ShiftPolicyCreate) => adminApi.createShiftPolicy(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "shift-policies"] });
      setShowShiftForm(false);
    },
  });

  const updateSP = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ShiftPolicy> }) =>
      adminApi.updateShiftPolicy(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "shift-policies"] });
      setEditingShift(null);
    },
  });

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Admin Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configure leave policies, shift policies, and system settings.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        <button
          onClick={() => setActiveTab("leave")}
          className={cn(
            "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "leave"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <TreePalm className="h-4 w-4" /> Leave Policies
        </button>
        <button
          onClick={() => setActiveTab("shifts")}
          className={cn(
            "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
            activeTab === "shifts"
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Clock className="h-4 w-4" /> Shift Policies
        </button>
      </div>

      {/* Leave Policies Tab */}
      {activeTab === "leave" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <TreePalm className="h-5 w-5 text-emerald-600" />
              Leave Types
            </CardTitle>
            {!showLeaveForm && !editingLeaveType && (
              <Button size="sm" onClick={() => setShowLeaveForm(true)}>
                <Plus className="mr-1 h-4 w-4" /> Add Leave Type
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {showLeaveForm && (
              <LeaveTypeForm
                onSave={(data) => createLT.mutate(data as adminApi.LeaveTypeCreate)}
                onCancel={() => setShowLeaveForm(false)}
              />
            )}

            {ltLoading ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                Loading leave types...
              </div>
            ) : leaveTypes.length === 0 ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                No leave types configured yet.
              </div>
            ) : (
              <div className="space-y-3">
                {leaveTypes.map((lt) =>
                  editingLeaveType?.id === lt.id ? (
                    <LeaveTypeForm
                      key={lt.id}
                      initial={lt}
                      onSave={(data) => updateLT.mutate({ id: lt.id, data })}
                      onCancel={() => setEditingLeaveType(null)}
                    />
                  ) : (
                    <div
                      key={lt.id}
                      className={cn(
                        "flex items-center justify-between rounded-lg border p-4 transition-colors",
                        lt.is_active
                          ? "border-border bg-card"
                          : "border-border/50 bg-muted/30 opacity-60"
                      )}
                    >
                      <div className="flex items-center gap-4">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700 font-bold text-xs">
                          {lt.code}
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{lt.name}</p>
                          <p className="text-xs text-muted-foreground">
                            Balance: {lt.default_balance} days · Carry: {lt.max_carry_forward}
                            {lt.is_paid ? " · Paid" : " · Unpaid"}
                            {lt.min_days_notice > 0 ? ` · ${lt.min_days_notice}d notice` : ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={lt.is_active ? "default" : "secondary"}>
                          {lt.is_active ? "Active" : "Inactive"}
                        </Badge>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => setEditingLeaveType(lt)}
                        >
                          <Edit3 className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() =>
                            updateLT.mutate({
                              id: lt.id,
                              data: { is_active: !lt.is_active },
                            })
                          }
                        >
                          {lt.is_active ? (
                            <ToggleRight className="h-4 w-4 text-emerald-600" />
                          ) : (
                            <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                          )}
                        </Button>
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Shift Policies Tab */}
      {activeTab === "shifts" && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-blue-600" />
              Shift Policies
            </CardTitle>
            {!showShiftForm && !editingShift && (
              <Button size="sm" onClick={() => setShowShiftForm(true)}>
                <Plus className="mr-1 h-4 w-4" /> Add Shift
              </Button>
            )}
          </CardHeader>
          <CardContent className="space-y-4">
            {showShiftForm && (
              <ShiftForm
                onSave={(data) => createSP.mutate(data as adminApi.ShiftPolicyCreate)}
                onCancel={() => setShowShiftForm(false)}
              />
            )}

            {spLoading ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                Loading shift policies...
              </div>
            ) : shifts.length === 0 ? (
              <div className="flex items-center justify-center py-8 text-muted-foreground">
                No shift policies configured yet.
              </div>
            ) : (
              <div className="space-y-3">
                {shifts.map((sp) =>
                  editingShift?.id === sp.id ? (
                    <ShiftForm
                      key={sp.id}
                      initial={sp}
                      onSave={(data) => updateSP.mutate({ id: sp.id, data })}
                      onCancel={() => setEditingShift(null)}
                    />
                  ) : (
                    <div
                      key={sp.id}
                      className={cn(
                        "flex items-center justify-between rounded-lg border p-4 transition-colors",
                        sp.is_active
                          ? "border-border bg-card"
                          : "border-border/50 bg-muted/30 opacity-60"
                      )}
                    >
                      <div className="flex items-center gap-4">
                        <div
                          className={cn(
                            "flex h-10 w-10 items-center justify-center rounded-lg font-bold text-xs",
                            sp.is_night_shift
                              ? "bg-indigo-50 text-indigo-700"
                              : "bg-amber-50 text-amber-700"
                          )}
                        >
                          {sp.is_night_shift ? (
                            <Moon className="h-5 w-5" />
                          ) : (
                            <Sun className="h-5 w-5" />
                          )}
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{sp.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {sp.start_time} – {sp.end_time} · Grace: {sp.grace_minutes} min ·
                            Half: {sp.half_day_minutes} min · Full: {sp.full_day_minutes} min
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={sp.is_active ? "default" : "secondary"}>
                          {sp.is_active ? "Active" : "Inactive"}
                        </Badge>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() => setEditingShift(sp)}
                        >
                          <Edit3 className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8"
                          onClick={() =>
                            updateSP.mutate({
                              id: sp.id,
                              data: { is_active: !sp.is_active },
                            })
                          }
                        >
                          {sp.is_active ? (
                            <ToggleRight className="h-4 w-4 text-blue-600" />
                          ) : (
                            <ToggleLeft className="h-4 w-4 text-muted-foreground" />
                          )}
                        </Button>
                      </div>
                    </div>
                  )
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
