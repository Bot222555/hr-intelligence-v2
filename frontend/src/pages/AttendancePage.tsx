import { Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export function AttendancePage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-foreground">Attendance</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Track daily attendance and time logs
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Clock className="h-12 w-12 text-muted-foreground/40" />
          <h3 className="mt-4 text-lg font-medium text-foreground">
            Attendance Tracker
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Coming soon — check-in/out times, overtime, and reports
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
