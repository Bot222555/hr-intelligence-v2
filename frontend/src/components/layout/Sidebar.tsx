import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Clock,
  Calendar,
  Settings,
  ChevronLeft,
  ChevronRight,
  UsersRound,
  FileEdit,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { ROUTES, ADMIN_ROLES, APP_NAME, APP_VERSION } from "@/lib/constants";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

interface NavItemDef {
  label: string;
  path: string;
  icon: typeof LayoutDashboard;
}

const NAV_ITEMS: NavItemDef[] = [
  { label: "Dashboard", path: ROUTES.DASHBOARD, icon: LayoutDashboard },
  { label: "Employees", path: ROUTES.EMPLOYEES, icon: Users },
  { label: "Attendance", path: ROUTES.ATTENDANCE, icon: Clock },
  { label: "Team Attendance", path: ROUTES.TEAM_ATTENDANCE, icon: UsersRound },
  { label: "Regularization", path: ROUTES.REGULARIZATION, icon: FileEdit },
  { label: "Leave", path: ROUTES.LEAVE, icon: Calendar },
];

const ADMIN_ITEMS: NavItemDef[] = [
  { label: "Settings", path: ROUTES.SETTINGS, icon: Settings },
];

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const { user } = useAuth();
  const isAdmin = user && ADMIN_ROLES.includes(user.role as (typeof ADMIN_ROLES)[number]);

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-30 flex h-screen flex-col border-r border-border bg-sidebar transition-all duration-300",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold text-sm">
          CF
        </div>
        {!collapsed && (
          <span className="truncate text-sm font-semibold text-foreground">
            {APP_NAME}
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <SidebarLink key={item.path} item={item} collapsed={collapsed} />
          ))}
        </ul>

        {isAdmin && (
          <>
            <div className="my-4 px-2">
              <div className="h-px bg-border" />
              {!collapsed && (
                <p className="mt-3 px-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Admin
                </p>
              )}
            </div>
            <ul className="space-y-1">
              {ADMIN_ITEMS.map((item) => (
                <SidebarLink
                  key={item.path}
                  item={item}
                  collapsed={collapsed}
                />
              ))}
            </ul>
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="border-t border-border p-2">
        <div className="flex items-center justify-between">
          {!collapsed && (
            <span className="px-2 text-xs text-muted-foreground">
              v{APP_VERSION}
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggle}
            className="h-8 w-8 shrink-0"
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </aside>
  );
}

function SidebarLink({
  item,
  collapsed,
}: {
  item: NavItemDef;
  collapsed: boolean;
}) {
  const Icon = item.icon;

  const link = (
    <NavLink
      to={item.path}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-primary-light text-primary"
            : "text-muted-foreground hover:bg-muted hover:text-foreground",
          collapsed && "justify-center px-2"
        )
      }
    >
      <Icon className="h-5 w-5 shrink-0" />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </NavLink>
  );

  if (collapsed) {
    return (
      <li>
        <Tooltip delayDuration={0}>
          <TooltipTrigger asChild>{link}</TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      </li>
    );
  }

  return <li>{link}</li>;
}
