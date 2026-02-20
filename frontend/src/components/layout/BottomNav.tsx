import { NavLink } from "react-router-dom";
import { LayoutDashboard, Users, Clock, Banknote, Receipt } from "lucide-react";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";

const NAV_ITEMS = [
  { label: "Home", path: ROUTES.DASHBOARD, icon: LayoutDashboard },
  { label: "People", path: ROUTES.EMPLOYEES, icon: Users },
  { label: "Attendance", path: ROUTES.ATTENDANCE, icon: Clock },
  { label: "Salary", path: ROUTES.SALARY, icon: Banknote },
  { label: "Expenses", path: ROUTES.EXPENSES, icon: Receipt },
];

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background sm:hidden">
      <div className="flex h-16 items-center justify-around">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-1 px-3 py-1 text-xs transition-colors",
                  isActive
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                )
              }
            >
              <Icon className="h-5 w-5" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}
