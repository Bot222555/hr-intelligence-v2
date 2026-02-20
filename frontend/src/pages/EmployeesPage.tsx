import { Users } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function EmployeesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Employees</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your team directory
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Users className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-medium text-foreground">
            Employee Directory
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Coming soon — search, filter, and manage employees
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
