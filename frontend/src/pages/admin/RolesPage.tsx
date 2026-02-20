/**
 * Admin Roles Page — View and assign roles to employees.
 * Only visible to system_admin and hr_admin roles.
 */

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Users,
  Shield,
  Crown,
  UserCog,
  User,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import * as adminApi from "@/api/admin";
// EmployeeRole type used implicitly via adminApi

const ROLE_CONFIG: Record<
  string,
  { label: string; color: string; bg: string; icon: typeof Shield }
> = {
  system_admin: {
    label: "System Admin",
    color: "text-red-700",
    bg: "bg-red-50 border-red-200",
    icon: Crown,
  },
  hr_admin: {
    label: "HR Admin",
    color: "text-purple-700",
    bg: "bg-purple-50 border-purple-200",
    icon: UserCog,
  },
  manager: {
    label: "Manager",
    color: "text-blue-700",
    bg: "bg-blue-50 border-blue-200",
    icon: Shield,
  },
  employee: {
    label: "Employee",
    color: "text-slate-600",
    bg: "bg-slate-50 border-slate-200",
    icon: User,
  },
};

const ROLE_OPTIONS = ["employee", "manager", "hr_admin", "system_admin"];

export function RolesPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>("");

  const { data: employees = [], isLoading } = useQuery({
    queryKey: ["admin", "roles"],
    queryFn: adminApi.getRoles,
  });

  const assignRole = useMutation({
    mutationFn: ({ employee_id, role }: { employee_id: string; role: string }) =>
      adminApi.assignRole(employee_id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "roles"] });
      setEditingId(null);
      setSelectedRole("");
    },
  });

  const filtered = useMemo(() => {
    let list = employees;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter(
        (e) =>
          e.display_name.toLowerCase().includes(q) ||
          e.email.toLowerCase().includes(q) ||
          e.employee_number.toLowerCase().includes(q)
      );
    }
    if (roleFilter !== "all") {
      list = list.filter((e) => e.role === roleFilter);
    }
    return list;
  }, [employees, search, roleFilter]);

  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = { all: employees.length };
    for (const e of employees) {
      counts[e.role] = (counts[e.role] || 0) + 1;
    }
    return counts;
  }, [employees]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Role Management</h1>
        <p className="text-sm text-muted-foreground">
          Assign and manage roles for all employees.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {ROLE_OPTIONS.map((role) => {
          const cfg = ROLE_CONFIG[role];
          const Icon = cfg.icon;
          return (
            <Card
              key={role}
              className={cn(
                "cursor-pointer transition-shadow hover:shadow-md",
                roleFilter === role && "ring-2 ring-primary"
              )}
              onClick={() => setRoleFilter(roleFilter === role ? "all" : role)}
            >
              <CardContent className="flex items-center gap-3 p-4">
                <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", cfg.bg)}>
                  <Icon className={cn("h-5 w-5", cfg.color)} />
                </div>
                <div>
                  <p className="text-2xl font-bold text-foreground">{roleCounts[role] || 0}</p>
                  <p className="text-xs text-muted-foreground">{cfg.label}s</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <input
          className="w-full rounded-lg border border-input bg-background py-2 pl-10 pr-4 text-sm placeholder:text-muted-foreground"
          placeholder="Search by name, email, or employee number..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Employee List */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Employees ({filtered.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              Loading employees...
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex items-center justify-center py-8 text-muted-foreground">
              No employees found.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th className="py-3 pr-4">Employee</th>
                    <th className="py-3 pr-4">Department</th>
                    <th className="py-3 pr-4">Current Role</th>
                    <th className="py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filtered.map((emp) => {
                    const cfg = ROLE_CONFIG[emp.role] || ROLE_CONFIG.employee;
                    const Icon = cfg.icon;
                    const isEditing = editingId === emp.employee_id;

                    return (
                      <tr key={emp.employee_id} className="group hover:bg-muted/30">
                        <td className="py-3 pr-4">
                          <div>
                            <p className="font-medium text-foreground">{emp.display_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {emp.employee_number} · {emp.email}
                            </p>
                          </div>
                        </td>
                        <td className="py-3 pr-4 text-muted-foreground">
                          {emp.department || "—"}
                        </td>
                        <td className="py-3 pr-4">
                          {isEditing ? (
                            <select
                              className="rounded-md border border-input bg-background px-2 py-1 text-sm"
                              value={selectedRole}
                              onChange={(e) => setSelectedRole(e.target.value)}
                            >
                              {ROLE_OPTIONS.map((r) => (
                                <option key={r} value={r}>
                                  {ROLE_CONFIG[r]?.label || r}
                                </option>
                              ))}
                            </select>
                          ) : (
                            <Badge
                              variant="outline"
                              className={cn("gap-1", cfg.bg, cfg.color)}
                            >
                              <Icon className="h-3 w-3" />
                              {cfg.label}
                            </Badge>
                          )}
                        </td>
                        <td className="py-3 text-right">
                          {isEditing ? (
                            <div className="flex justify-end gap-1">
                              <Button
                                size="sm"
                                variant="default"
                                disabled={assignRole.isPending}
                                onClick={() =>
                                  assignRole.mutate({
                                    employee_id: emp.employee_id,
                                    role: selectedRole,
                                  })
                                }
                              >
                                Save
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                  setEditingId(null);
                                  setSelectedRole("");
                                }}
                              >
                                Cancel
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="opacity-0 group-hover:opacity-100"
                              onClick={() => {
                                setEditingId(emp.employee_id);
                                setSelectedRole(emp.role);
                              }}
                            >
                              Change Role
                            </Button>
                          )}
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
