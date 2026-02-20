import { useState, useRef, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Menu, Bell, LogOut, User as UserIcon, Check } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn, getInitials } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import * as notificationsApi from "@/api/notifications";

interface HeaderProps {
  onMenuToggle: () => void;
}

const PAGE_TITLES: Record<string, string> = {
  [ROUTES.DASHBOARD]: "Dashboard",
  [ROUTES.EMPLOYEES]: "Employees",
  [ROUTES.ORG_CHART]: "Org Chart",
  [ROUTES.DEPARTMENTS]: "Departments",
  [ROUTES.ATTENDANCE]: "Attendance",
  [ROUTES.TEAM_ATTENDANCE]: "Team Attendance",
  [ROUTES.REGULARIZATION]: "Regularization",
  [ROUTES.LEAVE]: "Leave Management",
  [ROUTES.TEAM_LEAVE]: "Team Leave",
  [ROUTES.LEAVE_CALENDAR]: "Leave Calendar",
  [ROUTES.SALARY]: "Salary",
  [ROUTES.HELPDESK]: "Helpdesk",
  [ROUTES.EXPENSES]: "Expenses",
  [ROUTES.FNF]: "F&F Settlement",
  [ROUTES.SETTINGS]: "Settings",
  [ROUTES.ADMIN_ROLES]: "Roles & Permissions",
  [ROUTES.ADMIN_HOLIDAYS]: "Holidays",
};

const ROLE_LABELS: Record<string, string> = {
  employee: "Employee",
  manager: "Manager",
  hr_admin: "HR Admin",
  system_admin: "System Admin",
};

export function Header({ onMenuToggle }: HeaderProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const notifRef = useRef<HTMLDivElement>(null);

  const pageTitle = PAGE_TITLES[location.pathname] || "HR Intelligence";

  // ── Notifications ──────────────────────────────────────────────

  const { data: unreadData } = useQuery({
    queryKey: ["unreadCount"],
    queryFn: () => notificationsApi.getUnreadCount(),
    refetchInterval: 30_000, // poll every 30s
  });

  const { data: notifData, isLoading: loadingNotifs } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => notificationsApi.getNotifications({ page_size: 10 }),
    enabled: notifOpen,
  });

  const markAllReadMut = useMutation({
    mutationFn: () => notificationsApi.markAllAsRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["unreadCount"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  // The backend wraps in {data: {count}} or might return {count} directly
  const unreadCount = (unreadData as any)?.data?.count ?? (unreadData as any)?.count ?? 0;

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-border bg-background/80 px-4 backdrop-blur-sm lg:px-6">
      {/* Left: menu + title */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          onClick={onMenuToggle}
          className="lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <h1 className="text-lg font-semibold text-foreground">{pageTitle}</h1>
      </div>

      {/* Right: notifications + user */}
      <div className="flex items-center gap-2">
        {/* Notification bell */}
        <div className="relative" ref={notifRef}>
          <Button
            variant="ghost"
            size="icon"
            className="relative"
            onClick={() => setNotifOpen((v) => !v)}
          >
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </Button>

          {/* Notification dropdown */}
          {notifOpen && (
            <div className={cn(
              "absolute right-0 top-full mt-2 w-80 rounded-lg border border-border bg-popover shadow-lg",
              "animate-in fade-in-0 zoom-in-95",
            )}>
              <div className="flex items-center justify-between px-3 py-2 border-b">
                <p className="text-sm font-semibold text-popover-foreground">Notifications</p>
                {unreadCount > 0 && (
                  <button
                    onClick={() => markAllReadMut.mutate()}
                    className="flex items-center gap-1 text-xs text-primary hover:underline"
                    disabled={markAllReadMut.isPending}
                  >
                    <Check className="h-3 w-3" />
                    Mark all read
                  </button>
                )}
              </div>
              <div className="max-h-[320px] overflow-y-auto">
                {loadingNotifs ? (
                  <div className="flex justify-center py-6">
                    <span className="text-xs text-muted-foreground">Loading…</span>
                  </div>
                ) : (notifData?.data ?? []).length === 0 ? (
                  <div className="flex flex-col items-center py-8">
                    <Bell className="h-8 w-8 text-muted-foreground/40" />
                    <p className="mt-2 text-xs text-muted-foreground">No notifications</p>
                  </div>
                ) : (
                  (notifData?.data ?? []).map((n) => (
                    <div
                      key={n.id}
                      className={cn(
                        "px-3 py-2.5 border-b last:border-0 hover:bg-muted/50 transition-colors",
                        !n.is_read && "bg-primary/5",
                      )}
                    >
                      <p className="text-sm font-medium text-popover-foreground line-clamp-1">
                        {n.title}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                        {n.message}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg p-1.5 transition-colors hover:bg-muted"
          >
            <Avatar className="h-8 w-8">
              <AvatarImage src={user?.profile_picture_url ?? undefined} />
              <AvatarFallback className="bg-primary text-primary-foreground text-xs font-medium">
                {user ? getInitials(user.display_name) : "?"}
              </AvatarFallback>
            </Avatar>
            <span className="hidden text-sm font-medium text-foreground md:inline-block">
              {user?.display_name}
            </span>
          </button>

          {dropdownOpen && (
            <div
              className={cn(
                "absolute right-0 top-full mt-2 w-64 rounded-lg border border-border bg-popover p-1 shadow-lg",
                "animate-in fade-in-0 zoom-in-95"
              )}
            >
              <div className="px-3 py-2">
                <p className="text-sm font-medium text-popover-foreground">
                  {user?.display_name}
                </p>
                <p className="text-xs text-muted-foreground">{user?.email}</p>
                {user?.role && (
                  <Badge variant="secondary" className="mt-1.5 text-xs">
                    {ROLE_LABELS[user.role] || user.role}
                  </Badge>
                )}
              </div>

              <div className="my-1 h-px bg-border" />

              <button
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                onClick={() => {
                  setDropdownOpen(false);
                  if (user?.id) {
                    navigate(`/employees/${user.id}`);
                  }
                }}
              >
                <UserIcon className="h-4 w-4" />
                Profile
              </button>

              <button
                className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-danger transition-colors hover:bg-danger/10"
                onClick={() => {
                  setDropdownOpen(false);
                  logout();
                }}
              >
                <LogOut className="h-4 w-4" />
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
