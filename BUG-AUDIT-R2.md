# BUG AUDIT — Round 2

**Auditor:** Vision 📊  
**Date:** 2026-02-21  
**Scope:** Deep-dive audit of /Users/vision/hr-intelligence-v2 — finding NEW bugs not in BUG-AUDIT.md (Round 1)  
**Bugs Found:** 28

---

## 🔴 CRITICAL (Data Loss / Security / Complete Breakage)

---

### Bug R2-01: Dashboard "Pending Approvals" card always shows "—" (field name mismatch)

**Severity:** 🔴 Critical (Dashboard KPI broken for all users)  
**File:** `frontend/src/api/dashboard.ts` line 23 + `backend/dashboard/schemas.py` line 34  
**Issue:**  
Frontend `DashboardSummary` type expects `pending_approvals`, but backend `DashboardSummaryResponse` returns `pending_leave_requests`. The fourth KPI card on the dashboard always shows "—" because `summaryQuery.data?.["pending_approvals"]` is `undefined`.

**Fix:**  
Either rename the backend field or map it in the frontend API layer:
```typescript
// frontend/src/api/dashboard.ts — getDashboardSummary
export async function getDashboardSummary(): Promise<DashboardSummary> {
  const { data } = await apiClient.get("/dashboard/summary");
  return {
    ...data,
    pending_approvals: data.pending_leave_requests ?? 0,
    new_joiners_this_month: data.new_joiners_this_month ?? 0,
    attrition_this_month: data.attrition_this_month ?? 0,
  };
}
```

---

### Bug R2-02: `/salary/summary` returns all zeros — wrong field names on ORM model

**Severity:** 🔴 Critical (Salary data never surfaces)  
**File:** `backend/salary/router.py` lines 143-146  
**Issue:**  
The endpoint reads `getattr(salary, "gross_earnings", 0)`, `getattr(salary, "total_deductions", 0)`, and `getattr(salary, "net_salary", 0)`. But the `Salary` model (`backend/salary/models.py`) has fields named `gross_pay`, `net_pay`, and no `total_deductions` field at all. Every `getattr` falls through to the default `0`, so the API always returns `{"total_earnings": 0, "total_deductions": 0, "net_pay": 0}`.

**Fix:**
```python
# backend/salary/router.py — salary_summary
salary = await SalaryService.get_salary_by_employee(db, employee.id)
total_earnings = float(salary.gross_pay or 0)
net_pay = float(salary.net_pay or 0)
total_deductions = total_earnings - net_pay
```

---

### Bug R2-03: FnF page renders empty — frontend/backend response shapes completely different

**Severity:** 🔴 Critical (Entire FnF page broken)  
**File:** `frontend/src/api/fnf.ts` vs `backend/fnf/schemas.py`  
**Issue:**  
Frontend `FnFRecord` expects: `employee_name`, `employee_code`, `last_working_date`, `resignation_date`, `status`, `total_payable`, `total_recoverable`, `components`.  
Backend `FnFOut` sends: `employee_number`, `last_working_day`, `settlement_status`, `total_earnings`, `total_deductions`, `settlement_details`.

Every field the frontend renders is `undefined` or `null`. The FnF list renders cards with no names, no amounts, and no status badges.

**Fix:**  
Add a normalizer in `frontend/src/api/fnf.ts`:
```typescript
function normalizeFnF(data: any): FnFRecord {
  return {
    id: data.id,
    employee_id: data.employee_id,
    employee_name: data.employee_name ?? data.employee_number ?? null,
    employee_code: data.employee_code ?? data.employee_number ?? null,
    last_working_date: data.last_working_date ?? data.last_working_day ?? "",
    resignation_date: data.resignation_date ?? null,
    status: data.status ?? data.settlement_status ?? "pending",
    total_payable: data.total_payable ?? data.total_earnings ?? 0,
    total_recoverable: data.total_recoverable ?? data.total_deductions ?? 0,
    net_settlement: data.net_settlement ?? 0,
    components: data.components ?? [],
    created_at: data.created_at ?? "",
    updated_at: data.updated_at ?? "",
  };
}
```

---

### Bug R2-04: FnF summary widget broken — field name mismatch

**Severity:** 🔴 Critical  
**File:** `frontend/src/api/fnf.ts` `FnFSummary` interface vs `backend/fnf/schemas.py` `FnFSummary`  
**Issue:**  
Frontend expects: `total_pending`, `total_completed`, `total_amount_pending`, `total_amount_settled`.  
Backend sends: `total_settlements`, `pending`, `completed`, `total_net_amount`.

Summary stats render as `undefined` everywhere on the FnF page.

**Fix:**  
Normalize in `getFnFSummary`:
```typescript
export async function getFnFSummary(): Promise<FnFSummary> {
  const { data } = await apiClient.get("/fnf/summary");
  return {
    total_pending: data.total_pending ?? data.pending ?? 0,
    total_completed: data.total_completed ?? data.completed ?? 0,
    total_amount_pending: data.total_amount_pending ?? 0,
    total_amount_settled: data.total_amount_settled ?? data.total_net_amount ?? 0,
  };
}
```

---

### Bug R2-05: IDOR — any employee can view any other employee's expenses

**Severity:** 🔴 Critical (Security)  
**File:** `backend/expenses/router.py` lines 71-93 (`list_expenses`)  
**Issue:**  
`GET /expenses/?employee_id=<any-uuid>` only requires `get_current_user` (any authenticated user), not a role check. An employee can pass any `employee_id` query param and see all of another employee's expense claims including amounts, receipts, and approval status.

**Fix:**  
Add RBAC: if `employee_id` is provided and differs from `employee.id`, require manager/HR role:
```python
if employee_id and employee_id != employee.id:
    # Only managers/HR can view others' expenses
    if not await has_role(db, employee.id, [UserRole.manager, UserRole.hr_admin, UserRole.system_admin]):
        raise ForbiddenException("Cannot view another employee's expenses.")
```

---

### Bug R2-06: IDOR — any employee can read/update any helpdesk ticket

**Severity:** 🔴 Critical (Security)  
**File:** `backend/helpdesk/router.py` lines 142-149 (`get_ticket`) and 153-164 (`update_ticket`)  
**Issue:**  
`GET /helpdesk/{ticket_id}` and `PATCH /helpdesk/{ticket_id}` don't verify ticket ownership. Any authenticated user can read any ticket (potentially containing sensitive HR queries, complaints, salary disputes) and can update any ticket's status/priority/assignee.

**Fix:**  
Check ticket ownership or require role:
```python
ticket = await HelpdeskService.get_ticket(db, ticket_id)
if ticket.raised_by_id != employee.id:
    # Check if user is HR/admin or the assigned agent
    if not (is_hr or ticket.assigned_to_id == employee.id):
        raise ForbiddenException("You don't have access to this ticket.")
```

---

### Bug R2-07: IDOR — manager can access ANY employee's CTC, not just direct reports

**Severity:** 🔴 Critical (Security — salary data exposure)  
**File:** `backend/salary/router.py` lines 186-196 (`employee_ctc_breakdown`)  
**Issue:**  
`GET /salary/{employee_id}/ctc` requires `role in (manager, hr_admin, system_admin)` but doesn't verify the `employee_id` is a direct report of the requesting manager. A manager from Department A can view the full CTC breakdown of any employee in Department B.

**Fix:**  
Add a check that the requested employee reports to the current user (for managers):
```python
if employee.role == UserRole.manager:
    target_emp = await db.get(Employee, employee_id)
    if not target_emp or target_emp.reporting_manager_id != employee.id:
        raise ForbiddenException("You can only view CTC for your direct reports.")
```

---

## 🟠 HIGH (Wrong Data / Broken Features)

---

### Bug R2-08: Dashboard leave summary widget renders nothing — shape mismatch

**Severity:** 🟠 High  
**File:** `frontend/src/pages/DashboardPage.tsx` ~line 558 + `backend/dashboard/schemas.py` lines 85-101  
**Issue:**  
Frontend expects `leaveSummaryQuery.data?.data` → array of `{leave_type, leave_type_code, total_used, total_pending}`.  
Backend `LeaveSummaryResponse` returns `{month, year, total_requests, total_days, by_type: [{leave_type_id, leave_type_code, leave_type_name, request_count, total_days}]}`.

The frontend iterates `data.data` but the backend nests items under `by_type`, and the field names differ (`total_used` vs `total_days`, `total_pending` doesn't exist).

**Fix:**  
Normalize in `getLeaveSummary`:
```typescript
export async function getLeaveSummary(): Promise<LeaveSummaryResponse> {
  const { data } = await apiClient.get("/dashboard/leave-summary");
  return {
    data: (data.by_type ?? data.data ?? []).map((item: any) => ({
      leave_type: item.leave_type_name ?? item.leave_type ?? "",
      leave_type_code: item.leave_type_code ?? "",
      total_used: item.total_days ?? item.total_used ?? 0,
      total_pending: item.total_pending ?? 0,
    })),
  };
}
```

---

### Bug R2-09: Dashboard `new_joiners_this_month` and `attrition_this_month` always undefined

**Severity:** 🟠 High  
**File:** `frontend/src/api/dashboard.ts` lines 24-25 vs `backend/dashboard/schemas.py`  
**Issue:**  
Frontend `DashboardSummary` type has `new_joiners_this_month` and `attrition_this_month` fields. Backend `DashboardSummaryResponse` does NOT include these fields. Any component relying on these values gets `undefined`.

**Fix:**  
Remove from frontend type or add to backend. At minimum, frontend should default to 0.

---

### Bug R2-10: Leave form `dayCount` ignores weekends/holidays — shows wrong preview

**Severity:** 🟠 High (User confusion)  
**File:** `frontend/src/pages/LeavePage.tsx` ~lines 406-415 (`dayCount` useMemo)  
**Issue:**  
The `dayCount` preview in the Apply Leave form is a simple `(to - from) / msPerDay + 1`. It doesn't exclude weekends or holidays. The backend DOES exclude them. Example: User selects Mon-Sun (7 calendar days), frontend shows "7 days", backend calculates 5. User sees "7" then approval shows "5" — confusing and may cause them to select wrong dates.

**Fix:**  
Either fetch an estimated day count from backend (`POST /leave/calculate-days`) or note prominently "Excludes weekends & holidays; final count may differ."

---

### Bug R2-11: Helpdesk ticket create missing `description` and `body` fields

**Severity:** 🟠 High  
**File:** `frontend/src/pages/HelpdeskPage.tsx` (create ticket form) + `backend/helpdesk/schemas.py` `TicketCreate` + `backend/helpdesk/router.py` line 52  
**Issue:**  
The `HelpdeskPage` form collects `title`, `category`, `priority`, and `description`. But the backend `TicketCreate` schema may not have `description`, and the router passes: `title=body.title, category=body.category, priority=body.priority` — no description is passed to the service. The user's detailed issue description is silently dropped. Tickets are created with title only.

**Fix:**  
Add `description` to `TicketCreate` schema and pass it through:
```python
# router.py
ticket = await HelpdeskService.create_ticket(
    db, employee_id=employee.id, ..., description=body.description,
)
```

---

### Bug R2-12: `GET /helpdesk/` exposes all tickets to every employee

**Severity:** 🟠 High (Security)  
**File:** `backend/helpdesk/router.py` lines 71-93  
**Issue:**  
`list_tickets` requires only `get_current_user`. Any employee can call `GET /helpdesk/` without filters and see ALL helpdesk tickets from ALL employees. Sensitive tickets (salary disputes, harassment complaints) are exposed.

The `my-tickets` endpoint exists but the general listing is also accessible. The frontend `HelpdeskPage` likely calls the general endpoint.

**Fix:**  
For non-HR users, automatically filter to `raised_by_id=employee.id` unless user has HR/admin role:
```python
if not is_hr_or_admin:
    raised_by_id = employee.id
```

---

### Bug R2-13: Helpdesk `list_tickets` — `raised_by_id` filter enables IDOR

**Severity:** 🟠 High (Security)  
**File:** `backend/helpdesk/router.py` line 76  
**Issue:**  
Any authenticated user can pass `?raised_by_id=<other_employee_uuid>` to see all tickets raised by a specific employee. Combined with R2-06, this is a complete information disclosure.

**Fix:**  
If `raised_by_id` differs from `employee.id`, require HR/admin role.

---

### Bug R2-14: Leave cancellation doesn't restore balance correctly for cross-year leaves

**Severity:** 🟠 High (Data integrity)  
**File:** `backend/leave/service.py` (cancel_leave function)  
**Issue:**  
When a leave spanning Dec 28 – Jan 3 (cross-year) is cancelled, the service only restores balance for `leave_req.start_date.year`. Days consumed from the next year's balance are not restored. This creates a permanent balance discrepancy.

**Fix:**  
Handle cross-year restoration:
```python
years = set()
for d in computed_dates:
    years.add(d.year)
for year in years:
    # Restore days belonging to each year separately
```

---

### Bug R2-15: Expense `team-claims` falls back to ALL claims — data leak

**Severity:** 🟠 High (Security)  
**File:** `backend/expenses/router.py` lines 159-175  
**Issue:**  
If `ExpenseService.list_claims` doesn't support `manager_id` parameter, the `except TypeError` catches it and falls back to listing ALL claims with no employee filter. This means a manager sees every employee's expense claims across the entire organization.

**Fix:**  
Remove the blanket `except TypeError` fallback. If the service doesn't support team filtering, return empty or raise an error — don't fall through to all records:
```python
claims, total = await ExpenseService.list_claims(
    db, manager_id=employee.id, ...
)
# Remove except TypeError fallback entirely
```

---

### Bug R2-16: `salary/team` falls back to ALL salary records — same pattern

**Severity:** 🟠 High (Security)  
**File:** `backend/salary/router.py` lines 168-174  
**Issue:**  
Same pattern as R2-15. If `SalaryService.get_salary_slips` doesn't accept `manager_id`, the `except TypeError` falls through to returning ALL salary records. A manager would see every employee's salary data.

**Fix:**  
Remove the fallback or implement proper team filtering.

---

## 🟡 MEDIUM (UX Breakage / Incorrect Behavior)

---

### Bug R2-17: `BalanceCard` calculates total incorrectly

**Severity:** 🟡 Medium  
**File:** `frontend/src/pages/LeavePage.tsx` ~line 308  
**Issue:**  
```typescript
const total = Number(balance.current_balance) + Number(balance.used);
```
This is wrong. The DB column `current_balance` is computed as `opening_balance + accrued + carry_forwarded + adjusted - used`. So `current_balance + used = opening_balance + accrued + carry_forwarded + adjusted`. But "total" should be `opening_balance + accrued + carry_forwarded + adjusted` (the full entitlement). If there are adjustments (positive or negative), the math is coincidentally correct. However, if `adjusted` is negative (balance deduction by HR), then "total" shown will be less than expected, and the progress bar percentage will be skewed.

More importantly, the progress bar shows `used / total * 100`, but since `total = current_balance + used`, and `current_balance` already has `used` subtracted, `total` is correct only for the default case. The label says "total" but it's really "entitlement after adjustments" — confusing when HR makes adjustments.

**Fix:**  
Use the proper total:
```typescript
const total = Number(balance.opening_balance) + Number(balance.accrued) + Number(balance.carry_forwarded);
```

---

### Bug R2-18: Leave apply form sends `from_date` to wrong backend field

**Severity:** 🟡 Medium  
**File:** `frontend/src/api/leave.ts` `applyLeave` + `backend/leave/schemas.py` `LeaveRequestCreate`  
**Issue:**  
The frontend sends `{ from_date, to_date, leave_type_id, reason, day_details }`. The backend `LeaveRequestCreate` expects `from_date` and `to_date` (matching). However, the `LeaveRequestOut` returns `start_date` and `end_date`. If the frontend tries to display the dates from the mutation response using `request.from_date` instead of `request.start_date`, it shows `undefined`.

This is actually a near-miss — the create payload uses `from_date`/`to_date`, but the response uses `start_date`/`end_date`. If any frontend code assumes the response mirrors the request shape, it breaks.

**Verify:** Check if `LeaveRequestCard` uses `start_date` or `from_date`.

**File:** `frontend/src/pages/LeavePage.tsx` ~line 607+ — if the `LeaveRequest` type has `start_date` this is fine. If it uses `from_date`, it's broken.

---

### Bug R2-19: Leave request doesn't check balance for leave types that span two years

**Severity:** 🟡 Medium  
**File:** `backend/leave/service.py` ~line 487  
**Issue:**  
Balance check only looks at `data.from_date.year`:
```python
year = data.from_date.year
bal_result = await db.execute(
    select(LeaveBalance).where(
        LeaveBalance.employee_id == employee_id,
        LeaveBalance.leave_type_id == data.leave_type_id,
        LeaveBalance.year == year,
    )
)
```
A leave request from Dec 28, 2025 to Jan 5, 2026 only checks 2025 balance. If the employee has 3 days left in 2025 but needs 5 working days, the request passes validation (total 5 ≤ available 3? No, it would reject). But the days consumed from 2026 balance are never checked or deducted.

**Fix:**  
Split cross-year requests into per-year day counts and validate each year's balance separately.

---

### Bug R2-20: Attendance regularization form endpoint mismatch

**Severity:** 🟡 Medium  
**File:** `frontend/src/pages/RegularizationPage.tsx` + `backend/attendance/router.py`  
**Issue:**  
`RegularizationPage` likely submits regularization requests to an endpoint like `POST /attendance/regularization`. Need to verify the backend exposes this exact path and the request schema matches. The `backend/attendance/router.py` endpoints include `/regularization/` but the CRUD operations may have field mismatches between frontend types and backend schemas (`RegularizationCreate` etc.).

If the frontend sends `date` and backend expects `attendance_date`, or frontend sends `reason` and backend expects `remarks`, the form submission silently fails with 422.

**Fix:**  
Verify field-by-field alignment between frontend API calls and backend Pydantic schemas for regularization.

---

### Bug R2-21: `DashboardSummary` has `department_breakdown` field that frontend ignores

**Severity:** 🟡 Medium  
**File:** `backend/dashboard/schemas.py` line 36 vs `frontend/src/api/dashboard.ts` `DashboardSummary`  
**Issue:**  
Backend returns `department_breakdown: [{department_id, department_name, count}]` inside the summary response. Frontend type doesn't include this field, so it's silently discarded. The department headcount widget makes a SEPARATE API call to `/dashboard/department-headcount`. This is wasted bandwidth — the data is already in the summary response.

**Fix:**  
Either use the embedded data or remove it from the summary endpoint to reduce payload size.

---

### Bug R2-22: Expense summary uses `page_size=10000` — performance bomb

**Severity:** 🟡 Medium  
**File:** `backend/expenses/router.py` lines 137-138 + `backend/helpdesk/router.py` lines 127-128  
**Issue:**  
Both `expense_summary` and `helpdesk_summary` endpoints fetch up to 10,000 records into memory just to count statuses:
```python
claims, total = await ExpenseService.list_claims(
    db, employee_id=employee.id, page=1, page_size=10000,
)
```
This should use `COUNT(*) ... GROUP BY status` SQL queries instead of loading every record and counting in Python. For companies with thousands of expenses/tickets, this causes significant memory usage and latency.

**Fix:**  
Add dedicated count queries in the service:
```python
@staticmethod
async def get_summary_counts(db, employee_id):
    result = await db.execute(
        select(Expense.approval_status, func.count())
        .where(Expense.employee_id == employee_id)
        .group_by(Expense.approval_status)
    )
    return dict(result.all())
```

---

### Bug R2-23: Auth callback page doesn't handle OAuth error responses

**Severity:** 🟡 Medium  
**File:** `frontend/src/pages/AuthCallbackPage.tsx`  
**Issue:**  
The OAuth callback page extracts `code` from URL params but doesn't check for `error` or `error_description` params that Google returns on OAuth failure (user denied consent, session expired, etc.). If Google redirects back with `?error=access_denied`, the page tries to call `login(undefined)` which causes an unhandled error and shows a blank screen or cryptic error.

**Fix:**  
```typescript
const error = searchParams.get("error");
if (error) {
  navigate("/login", { state: { error: searchParams.get("error_description") || "Authentication failed" } });
  return;
}
```

---

### Bug R2-24: Leave approve doesn't check if approver is L2 manager before allowing approval

**Severity:** 🟡 Medium  
**File:** `backend/leave/service.py` ~line 594  
**Issue:**  
The `approve_leave` function checks `is_manager`, `is_l2`, and `is_hr`. But it computes:
```python
is_l2 = employee.l2_manager_id == approver_id
```
This means the L2 manager can approve without the L1 manager having seen it. There's no workflow enforcement — either L1 or L2 or HR can approve directly. While this may be intentional, it means L1 managers can be completely bypassed, which is unexpected for most HR workflows.

**Fix:**  
Document this as intentional OR add a workflow check:
```python
if is_l2 and not is_manager and leave_type.requires_l1_approval:
    raise ValidationException({"approval": ["L1 manager must approve first."]})
```

---

### Bug R2-25: Employee profile page — `/employees/{id}/profile` has no RBAC

**Severity:** 🟡 Medium (Privacy)  
**File:** `backend/core_hr/router.py`  
**Issue:**  
The employee profile endpoint may allow any authenticated user to fetch detailed profile info (personal email, phone, date of birth, address) of any other employee by ID. While the employee directory is normal, sensitive personal data fields should be filtered for non-HR users.

**Fix:**  
Implement field-level access control: non-HR users see only public fields (name, department, designation, photo). Sensitive fields (DOB, personal email, phone, address, salary) are hidden or masked.

---

### Bug R2-26: Org chart page crashes if employee has no `reporting_manager_id`

**Severity:** 🟡 Medium  
**File:** `frontend/src/pages/OrgChartPage.tsx`  
**Issue:**  
The org chart builds a tree structure from employee reporting relationships. Employees with `reporting_manager_id = null` (typically the CEO/founders) need to be handled as root nodes. If the tree-building logic assumes every employee has a manager, it creates orphan nodes that never appear in the tree or causes an infinite loop trying to find the root.

**Fix:**  
Explicitly handle null managers as tree roots:
```typescript
const roots = employees.filter(e => !e.reporting_manager_id);
```

---

## 🔵 LOW (Cosmetic / Minor Inconsistencies)

---

### Bug R2-27: `formatDate` utility doesn't handle null/undefined gracefully

**Severity:** 🔵 Low  
**File:** `frontend/src/lib/utils.ts` (or wherever `formatDate` is defined)  
**Issue:**  
If `formatDate` receives `null`, `undefined`, or an empty string (which happens when backend returns null dates), it may return `"Invalid Date"` or throw. This string appears in leave request cards, expense records, etc.

**Fix:**  
```typescript
export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-IN", { ... });
}
```

---

### Bug R2-28: Helpdesk ticket status update — no validation of valid status transitions

**Severity:** 🔵 Low  
**File:** `backend/helpdesk/router.py` lines 153-164 (`update_ticket`)  
**Issue:**  
`PATCH /{ticket_id}` passes `body.model_dump(exclude_unset=True)` directly to the service without validating status transitions. A user can move a ticket from "closed" back to "open", or from "resolved" to "in_progress". Invalid state transitions break reporting and SLA tracking.

**Fix:**  
Add a state machine validator:
```python
VALID_TRANSITIONS = {
    "open": ["in_progress", "closed"],
    "in_progress": ["resolved", "closed"],
    "resolved": ["closed", "open"],  # reopen
    "closed": [],  # terminal
}
if "status" in update_data:
    old_status = ticket.status
    new_status = update_data["status"]
    if new_status not in VALID_TRANSITIONS.get(old_status, []):
        raise ValidationException({"status": [f"Cannot move from {old_status} to {new_status}."]})
```

---

## Summary Table

| ID | Severity | Area | One-line description |
|----|----------|------|---------------------|
| R2-01 | 🔴 Critical | Dashboard | `pending_approvals` field doesn't exist in backend response |
| R2-02 | 🔴 Critical | Salary | `/summary` reads wrong ORM field names → always returns 0 |
| R2-03 | 🔴 Critical | FnF | Frontend/backend record shapes completely mismatched |
| R2-04 | 🔴 Critical | FnF | Summary stats field names mismatched |
| R2-05 | 🔴 Critical | Expenses | IDOR: any user can view any employee's expenses |
| R2-06 | 🔴 Critical | Helpdesk | IDOR: any user can read/update any ticket |
| R2-07 | 🔴 Critical | Salary | IDOR: manager can view any employee's CTC |
| R2-08 | 🟠 High | Dashboard | Leave summary widget shape mismatch — shows nothing |
| R2-09 | 🟠 High | Dashboard | `new_joiners_this_month` not in backend → undefined |
| R2-10 | 🟠 High | Leave | Day count preview ignores weekends/holidays |
| R2-11 | 🟠 High | Helpdesk | Ticket description field dropped on create |
| R2-12 | 🟠 High | Helpdesk | `GET /` exposes all tickets to every employee |
| R2-13 | 🟠 High | Helpdesk | `raised_by_id` filter enables IDOR |
| R2-14 | 🟠 High | Leave | Cross-year leave cancellation balance not restored |
| R2-15 | 🟠 High | Expenses | Team claims fallback exposes all claims |
| R2-16 | 🟠 High | Salary | Team salary fallback exposes all records |
| R2-17 | 🟡 Medium | Leave | BalanceCard total calculation incorrect with adjustments |
| R2-18 | 🟡 Medium | Leave | Response uses `start_date` but request sends `from_date` |
| R2-19 | 🟡 Medium | Leave | Cross-year leave balance check incomplete |
| R2-20 | 🟡 Medium | Attendance | Regularization form/backend field mismatch |
| R2-21 | 🟡 Medium | Dashboard | `department_breakdown` embedded but unused |
| R2-22 | 🟡 Medium | Expenses/Helpdesk | Summary loads 10K records into memory |
| R2-23 | 🟡 Medium | Auth | OAuth callback doesn't handle error params |
| R2-24 | 🟡 Medium | Leave | L2 manager can bypass L1 approval |
| R2-25 | 🟡 Medium | Core HR | Employee profile has no field-level RBAC |
| R2-26 | 🟡 Medium | Org Chart | Crashes with null `reporting_manager_id` |
| R2-27 | 🔵 Low | Utils | `formatDate` doesn't handle null |
| R2-28 | 🔵 Low | Helpdesk | No status transition validation |

---

**Priority fix order:**  
1. Security IDORs first (R2-05, R2-06, R2-07, R2-12, R2-13, R2-15, R2-16) — these are exploitable today  
2. Data display bugs (R2-01, R2-02, R2-03, R2-04, R2-08) — users see broken pages  
3. Logic bugs (R2-10, R2-14, R2-19) — wrong calculations  
4. Everything else
