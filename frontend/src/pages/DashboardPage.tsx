import { useAuth } from "@/hooks/useAuth";
import { Card, CardContent } from "@/components/ui/card";
import { LayoutDashboard, Users, Clock, Calendar } from "lucide-react";

const STAT_CARDS = [
  { label: "Total Employees", value: "—", icon: Users, color: "text-primary" },
  { label: "Present Today", value: "—", icon: Clock, color: "text-success" },
  { label: "On Leave", value: "—", icon: Calendar, color: "text-warning" },
  { label: "Departments", value: "—", icon: LayoutDashboard, color: "text-info" },
];

export function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Greeting */}
      <div>
        <h2 className="text-2xl font-bold text-foreground">
          Welcome back, {user?.display_name?.split(" ")[0] || "there"}!
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Here's what's happening at Creativefuel today
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {STAT_CARDS.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label}>
              <CardContent className="flex items-center gap-4 p-5">
                <div className="rounded-lg bg-muted p-2.5">
                  <Icon className={`h-5 w-5 ${stat.color}`} />
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{stat.label}</p>
                  <p className="text-2xl font-bold text-foreground">
                    {stat.value}
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Placeholder */}
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <LayoutDashboard className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-medium text-foreground">
            Dashboard
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Charts and analytics coming soon
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
