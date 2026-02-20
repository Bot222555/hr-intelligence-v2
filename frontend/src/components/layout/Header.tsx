import { useState, useRef, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { Menu, Bell, LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { cn, getInitials } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";

interface HeaderProps {
  onMenuToggle: () => void;
}

const PAGE_TITLES: Record<string, string> = {
  [ROUTES.DASHBOARD]: "Dashboard",
  [ROUTES.EMPLOYEES]: "Employees",
  [ROUTES.ATTENDANCE]: "Attendance",
  [ROUTES.TEAM_ATTENDANCE]: "Team Attendance",
  [ROUTES.REGULARIZATION]: "Regularization",
  [ROUTES.LEAVE]: "Leave Management",
  [ROUTES.SETTINGS]: "Settings",
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
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const pageTitle = PAGE_TITLES[location.pathname] || "HR Intelligence";

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setDropdownOpen(false);
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
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          <span className="absolute right-1.5 top-1.5 flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
          </span>
        </Button>

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
                onClick={() => setDropdownOpen(false)}
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
