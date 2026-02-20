/**
 * DepartmentsPage — Grid of department cards with search/filter.
 * Click a card → department detail (members list).
 */

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Building2,
  Users,
  MapPin,
  Search,
  Loader2,
  AlertCircle,
  UserCircle,
  ArrowRight,
} from "lucide-react";
import { getDepartmentsList, type DepartmentDetail } from "@/api/orgchart";
import { Input } from "@/components/ui/input";
// utils imported as needed

// ── Department Card ────────────────────────────────────────────────

function DepartmentCard({ dept }: { dept: DepartmentDetail }) {
  const navigate = useNavigate();

  return (
    <div
      onClick={() => navigate(`/departments/${dept.id}`)}
      className="group relative flex flex-col gap-3 rounded-xl border bg-card p-5 shadow-sm transition-all hover:shadow-md hover:border-primary/30 cursor-pointer"
    >
      {/* Header: icon + name */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Building2 className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground leading-tight group-hover:text-primary transition-colors">
              {dept.name}
            </h3>
            {dept.code && (
              <span className="text-xs text-muted-foreground">{dept.code}</span>
            )}
          </div>
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-1" />
      </div>

      {/* Description */}
      {dept.description && (
        <p className="text-xs text-muted-foreground line-clamp-2">
          {dept.description}
        </p>
      )}

      {/* Stats */}
      <div className="flex flex-wrap items-center gap-4 pt-1 border-t border-border/50">
        {/* Department Head */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <UserCircle className="h-3.5 w-3.5" />
          <span>{dept.head_employee_name || "No head assigned"}</span>
        </div>

        {/* Employee count */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Users className="h-3.5 w-3.5" />
          <span>
            {dept.employee_count} member{dept.employee_count !== 1 ? "s" : ""}
          </span>
        </div>

        {/* Location */}
        {dept.location && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin className="h-3.5 w-3.5" />
            <span>{dept.location.city || dept.location.name}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────

export function DepartmentsPage() {
  const [searchTerm, setSearchTerm] = useState("");

  const {
    data: deptData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["departments-list"],
    queryFn: getDepartmentsList,
  });

  // Filter departments
  const filtered = useMemo(() => {
    if (!deptData?.data) return [];
    if (!searchTerm.trim()) return deptData.data;
    const q = searchTerm.toLowerCase();
    return deptData.data.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        (d.code?.toLowerCase().includes(q) ?? false) ||
        (d.head_employee_name?.toLowerCase().includes(q) ?? false) ||
        (d.location?.name.toLowerCase().includes(q) ?? false) ||
        (d.location?.city?.toLowerCase().includes(q) ?? false)
    );
  }, [deptData, searchTerm]);

  // Stats
  const totalDepts = deptData?.data.length ?? 0;
  const totalMembers = deptData?.data.reduce((a, d) => a + d.employee_count, 0) ?? 0;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b bg-background px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Building2 className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Departments</h1>
            <p className="text-sm text-muted-foreground">
              {totalDepts} department{totalDepts !== 1 ? "s" : ""} · {totalMembers} total members
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder="Search departments..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-64 pl-9"
          />
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {isLoading && (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-3 text-muted-foreground">Loading departments…</span>
          </div>
        )}

        {error && (
          <div className="flex h-64 items-center justify-center">
            <AlertCircle className="h-6 w-6 text-destructive" />
            <span className="ml-2 text-destructive">Failed to load departments</span>
          </div>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex h-64 flex-col items-center justify-center text-muted-foreground">
            <Building2 className="h-12 w-12 mb-3 opacity-40" />
            <p className="text-lg font-medium">
              {searchTerm ? "No departments match your search" : "No departments found"}
            </p>
          </div>
        )}

        {!isLoading && !error && filtered.length > 0 && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((dept) => (
              <DepartmentCard key={dept.id} dept={dept} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
