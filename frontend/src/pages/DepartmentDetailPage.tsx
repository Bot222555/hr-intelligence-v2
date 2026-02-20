/**
 * DepartmentDetailPage — Shows all members of a specific department.
 *
 * URL: /departments/:departmentId
 */

import { useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Building2,
  Users,
  MapPin,
  UserCircle,
  Search,
  Loader2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Mail,
  Phone,
} from "lucide-react";
import {
  getDepartmentDetail,
  getDepartmentMembers,
} from "@/api/orgchart";
import type { EmployeeListItem } from "@/api/employees";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const PAGE_SIZE = 20;

// ── Member Row ─────────────────────────────────────────────────────

function MemberRow({ emp }: { emp: EmployeeListItem }) {
  const navigate = useNavigate();
  const initials = (emp.display_name || `${emp.first_name} ${emp.last_name}`)
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const statusColor: Record<string, string> = {
    active: "bg-emerald-100 text-emerald-700",
    notice_period: "bg-amber-100 text-amber-700",
    relieved: "bg-slate-100 text-slate-600",
    absconding: "bg-red-100 text-red-700",
  };

  return (
    <div
      onClick={() =>
        navigate(`/employees?search=${encodeURIComponent(emp.employee_code)}`)
      }
      className="flex items-center gap-4 rounded-lg border bg-card p-4 transition-all hover:shadow-sm hover:border-primary/30 cursor-pointer"
    >
      {/* Avatar */}
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm overflow-hidden">
        {emp.profile_photo_url ? (
          <img
            src={emp.profile_photo_url}
            alt={emp.display_name || ""}
            className="h-full w-full object-cover rounded-full"
          />
        ) : (
          initials
        )}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-foreground truncate">
            {emp.display_name || `${emp.first_name} ${emp.last_name}`}
          </span>
          <span className="text-xs text-muted-foreground">
            {emp.employee_code}
          </span>
          <Badge
            variant="secondary"
            className={cn(
              "text-[10px] px-1.5 py-0",
              statusColor[emp.employment_status] || ""
            )}
          >
            {emp.employment_status.replace("_", " ")}
          </Badge>
        </div>
        <div className="flex items-center gap-3 mt-0.5">
          {emp.designation && (
            <span className="text-xs text-muted-foreground truncate">
              {emp.designation}
            </span>
          )}
        </div>
      </div>

      {/* Contact */}
      <div className="hidden md:flex items-center gap-4 shrink-0">
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Mail className="h-3 w-3" />
          <span className="truncate max-w-[180px]">{emp.email}</span>
        </div>
        {emp.phone && (
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Phone className="h-3 w-3" />
            <span>{emp.phone}</span>
          </div>
        )}
      </div>

      {/* Location */}
      {emp.location && (
        <div className="hidden lg:flex items-center gap-1 text-xs text-muted-foreground shrink-0">
          <MapPin className="h-3 w-3" />
          <span>{emp.location.city || emp.location.name}</span>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────

export function DepartmentDetailPage() {
  const { departmentId } = useParams<{ departmentId: string }>();
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);

  // Fetch department detail
  const { data: deptResp, isLoading: deptLoading } = useQuery({
    queryKey: ["department-detail", departmentId],
    queryFn: () => getDepartmentDetail(departmentId!),
    enabled: !!departmentId,
  });

  // Fetch members (paginated)
  const {
    data: membersResp,
    isLoading: membersLoading,
    error: membersError,
  } = useQuery({
    queryKey: ["department-members", departmentId, page, searchTerm],
    queryFn: () =>
      getDepartmentMembers(departmentId!, {
        page,
        page_size: PAGE_SIZE,
        search: searchTerm || undefined,
      }),
    enabled: !!departmentId,
  });

  const dept = deptResp?.data;
  const members = membersResp?.data ?? [];
  const meta = membersResp?.meta;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b bg-background px-6 py-4">
        {/* Back link */}
        <Link
          to="/departments"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-3"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Departments
        </Link>

        {deptLoading && (
          <div className="flex items-center gap-2">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
            <span className="text-muted-foreground">Loading…</span>
          </div>
        )}

        {dept && (
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                <Building2 className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-foreground">
                  {dept.name}
                  {dept.code && (
                    <span className="ml-2 text-sm font-normal text-muted-foreground">
                      ({dept.code})
                    </span>
                  )}
                </h1>
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  {dept.head_employee_name && (
                    <span className="flex items-center gap-1">
                      <UserCircle className="h-3.5 w-3.5" />
                      {dept.head_employee_name}
                    </span>
                  )}
                  <span className="flex items-center gap-1">
                    <Users className="h-3.5 w-3.5" />
                    {dept.employee_count} member{dept.employee_count !== 1 ? "s" : ""}
                  </span>
                  {dept.location && (
                    <span className="flex items-center gap-1">
                      <MapPin className="h-3.5 w-3.5" />
                      {dept.location.city || dept.location.name}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search members..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setPage(1);
                }}
                className="w-64 pl-9"
              />
            </div>
          </div>
        )}
      </div>

      {/* Members list */}
      <div className="flex-1 overflow-y-auto p-6">
        {membersLoading && (
          <div className="flex h-48 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-3 text-muted-foreground">Loading members…</span>
          </div>
        )}

        {membersError && (
          <div className="flex h-48 items-center justify-center">
            <AlertCircle className="h-6 w-6 text-destructive" />
            <span className="ml-2 text-destructive">Failed to load members</span>
          </div>
        )}

        {!membersLoading && !membersError && members.length === 0 && (
          <div className="flex h-48 flex-col items-center justify-center text-muted-foreground">
            <Users className="h-12 w-12 mb-3 opacity-40" />
            <p className="text-lg font-medium">
              {searchTerm ? "No members match your search" : "No members in this department"}
            </p>
          </div>
        )}

        {!membersLoading && !membersError && members.length > 0 && (
          <div className="space-y-2">
            {members.map((emp) => (
              <MemberRow key={emp.id} emp={emp} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {meta && meta.total_pages > 1 && (
          <div className="flex items-center justify-between border-t pt-4 mt-4">
            <span className="text-sm text-muted-foreground">
              Page {meta.page} of {meta.total_pages} ({meta.total} total)
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!meta.has_prev}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!meta.has_next}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
