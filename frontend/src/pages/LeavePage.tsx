import { Calendar } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function LeavePage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Leave Management</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Apply for leave and track balances
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Calendar className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-medium text-foreground">
            Leave Management
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Coming soon — apply, approve, and track leave requests
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
