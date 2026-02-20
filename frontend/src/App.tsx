import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/AuthContext";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { AuthCallbackPage } from "@/pages/AuthCallbackPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { EmployeesPage } from "@/pages/EmployeesPage";
import { AttendancePage } from "@/pages/AttendancePage";
import { TeamAttendancePage } from "@/pages/TeamAttendancePage";
import { RegularizationPage } from "@/pages/RegularizationPage";
import { LeavePage } from "@/pages/LeavePage";
import { TeamLeavePage } from "@/pages/TeamLeavePage";
import { LeaveCalendar } from "@/pages/LeaveCalendar";
import { SalaryPage } from "@/pages/SalaryPage";
import { HelpdeskPage } from "@/pages/HelpdeskPage";
import { ExpensesPage } from "@/pages/ExpensesPage";
import { OrgChartPage } from "@/pages/OrgChartPage";
import { DepartmentsPage } from "@/pages/DepartmentsPage";
import { DepartmentDetailPage } from "@/pages/DepartmentDetailPage";
import { NotFoundPage } from "@/pages/NotFoundPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 5 * 60 * 1000, // 5 minutes
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <BrowserRouter>
          <AuthProvider>
            <Routes>
              {/* Public */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/auth/callback" element={<AuthCallbackPage />} />

              {/* Protected */}
              <Route path="/" element={<AppShell />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="employees" element={<EmployeesPage />} />
                <Route path="org-chart" element={<OrgChartPage />} />
                <Route path="departments" element={<DepartmentsPage />} />
                <Route path="departments/:departmentId" element={<DepartmentDetailPage />} />
                <Route path="attendance" element={<AttendancePage />} />
                <Route path="attendance/team" element={<TeamAttendancePage />} />
                <Route path="attendance/regularization" element={<RegularizationPage />} />
                <Route path="leave" element={<LeavePage />} />
                <Route path="leave/team" element={<TeamLeavePage />} />
                <Route path="leave/calendar" element={<LeaveCalendar />} />
                <Route path="salary" element={<SalaryPage />} />
                <Route path="helpdesk" element={<HelpdeskPage />} />
                <Route path="expenses" element={<ExpensesPage />} />
              </Route>

              {/* 404 */}
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
