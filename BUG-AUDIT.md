# 🐛 HR Intelligence v2 — Full Bug Audit

**Date:** 2026-02-20  
**Auditor:** Vision 📊  
**Scope:** Frontend ↔ Backend API mismatches, broken routes, missing features, data issues

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical (breaks functionality) | 18 |
| 🟡 High (wrong data/behavior) | 14 |
| 🔵 Medium (UX issues) | 10 |
| ⚪ Low (cosmetic/cleanup) | 6 |
| **Total** | **48** |

---

## 🔴 Critical — Breaks Functionality

### BUG-001: Salary — Frontend calls `/salary/my-slips` but backend has `/salary/slips`
- **Frontend:** `frontend/src/api/salary.ts:92` — `GET /salary/my-slips`
- **Backend:** `backend/salary/router.py:72` — `GET /salary/slips` (HR-only, requires `hr_admin`/`system_admin`)
- **Impact:** Employee salary slip page returns 404 for all users. The backend `/slips` endpoint is HR-only and doesn't filter by current user — there's no employee self-service salary slip endpoint at all.
- **Fix:** Add `GET /my-slips` endpoint in `backend/salary/router.py` that filters by `employee.id` and returns paginated slips. Also needs a salary_slips table or a way to generate monthly slips from the salaries table.

### BUG-002: Salary — Frontend calls `/salary/ctc-breakdown` but backend has `/salary/my-ctc`
- **Frontend:** `frontend/src/api/salary.ts:109` — `GET /salary/ctc-breakdown`
- **Backend:** `backend/salary/router.py:60` — `GET /salary/my-ctc`
- **Impact:** CTC breakdown tab returns 404 for all employees.
- **Fix:** Change frontend to call `/salary/my-ctc` or add alias route in backend.

### BUG-003: Salary — Frontend calls `/salary/team` but no team endpoint exists in backend
- **Frontend:** `frontend/src/api/salary.ts:117` — `GET /salary/team`
- **Backend:** No matching route exists in `backend/salary/router.py`
- **Impact:** Team salary tab for managers returns 404.
- **Fix:** Add `GET /team` endpoint in backend salary router that returns team salary data for the manager's direct reports.

### BUG-004: Salary — Frontend calls `/salary/summary` but no summary endpoint exists in backend
- **Frontend:** `frontend/src/api/salary.ts:122` — `GET /salary/summary`
- **Backend:** No matching route exists in `backend/salary/router.py`
- **Impact:** Dashboard salary widget returns 404 (silently fails).
- **Fix:** Add `GET /summary` endpoint returning last month net/gross, YTD, next payroll date.

### BUG-005: Salary — Frontend calls `/salary/slips/{slipId}` and `/salary/slips/{slipId}/pdf` — no matching routes
- **Frontend:** `frontend/src/api/salary.ts:97-103` — `GET /salary/slips/{slipId}` and `GET /salary/slips/{slipId}/pdf`
- **Backend:** No individual slip or PDF download routes exist
- **Impact:** Clicking a salary slip and the PDF download button both return 404.
- **Fix:** Add `GET /slips/{slip_id}` and `GET /slips/{slip_id}/pdf` endpoints.

### BUG-006: Expenses — Frontend calls `/expenses/my-claims` but backend has `/expenses/my-expenses`
- **Frontend:** `frontend/src/api/expenses.ts:94` — `GET /expenses/my-claims`
- **Backend:** `backend/expenses/router.py:81` — `GET /expenses/my-expenses`
- **Impact:** My Expenses page returns 404 for all users.
- **Fix:** Change frontend to `/expenses/my-expenses` or rename backend route.

### BUG-007: Expenses — Frontend calls `POST /expenses/claims` but backend has `POST /expenses/`
- **Frontend:** `frontend/src/api/expenses.ts:110` — `POST /expenses/claims`
- **Backend:** `backend/expenses/router.py:30` — `POST /expenses/`
- **Impact:** Creating new expense claims returns 404.
- **Fix:** Change frontend to `POST /expenses/` or add `/claims` route alias.

### BUG-008: Expenses — Frontend calls `GET /expenses/claims/{id}` but backend has `GET /expenses/{id}`
- **Frontend:** `frontend/src/api/expenses.ts:99` — `GET /expenses/claims/{claimId}`
- **Backend:** `backend/expenses/router.py:107` — `GET /expenses/{claim_id}`
- **Impact:** Expense claim detail view returns 404.
- **Fix:** Change frontend to `GET /expenses/{claimId}`.

### BUG-009: Expenses — Frontend calls `PUT /expenses/claims/{id}/approve` but backend uses `POST` method
- **Frontend:** `frontend/src/api/expenses.ts:137` — `PUT /expenses/claims/{claimId}/approve`
- **Backend:** `backend/expenses/router.py:141` — `POST /expenses/{claim_id}/approve`
- **Impact:** Approving expenses fails — wrong HTTP method AND wrong URL path (`/claims/` prefix).
- **Fix:** Change frontend to `POST /expenses/${claimId}/approve` (drop `/claims/` and change to POST).

### BUG-010: Expenses — Frontend calls `PUT /expenses/claims/{id}/reject` but backend uses `POST` method
- **Frontend:** `frontend/src/api/expenses.ts:147` — `PUT /expenses/claims/{claimId}/reject`
- **Backend:** `backend/expenses/router.py:160` — `POST /expenses/{claim_id}/reject`
- **Impact:** Rejecting expenses fails — wrong method AND wrong URL.
- **Fix:** Change frontend to `POST /expenses/${claimId}/reject`.

### BUG-011: Expenses — Frontend calls `/expenses/team-claims` but no team endpoint exists
- **Frontend:** `frontend/src/api/expenses.ts:129` — `GET /expenses/team-claims`
- **Backend:** No matching route (only `GET /expenses/` with optional `employee_id` filter)
- **Impact:** Team expenses tab for managers returns 404.
- **Fix:** Either add `GET /team-claims` (filter to direct reports) or change frontend to use `GET /expenses/` with team filtering.

### BUG-012: Expenses — Frontend calls `/expenses/upload-receipt` but no upload endpoint exists
- **Frontend:** `frontend/src/api/expenses.ts:117` — `POST /expenses/upload-receipt`
- **Backend:** No file upload route exists in `backend/expenses/router.py`
- **Impact:** Receipt upload button fails with 404.
- **Fix:** Add file upload endpoint in backend or use an external file storage integration.

### BUG-013: Expenses — Frontend calls `/expenses/summary` but no summary endpoint exists
- **Frontend:** `frontend/src/api/expenses.ts:157` — `GET /expenses/summary`
- **Backend:** No matching route in `backend/expenses/router.py`
- **Impact:** Expense summary cards on the expenses page and dashboard return 404.
- **Fix:** Add `GET /summary` endpoint in expenses router.

### BUG-014: Helpdesk — Frontend calls `POST /helpdesk/tickets` but backend has `POST /helpdesk/`
- **Frontend:** `frontend/src/api/helpdesk.ts:115` — `POST /helpdesk/tickets`
- **Backend:** `backend/helpdesk/router.py:31` — `POST /helpdesk/`
- **Impact:** Creating new tickets returns 404.
- **Fix:** Change frontend to `POST /helpdesk/`.

### BUG-015: Helpdesk — Frontend calls `GET /helpdesk/tickets/{id}` but backend has `GET /helpdesk/{id}`
- **Frontend:** `frontend/src/api/helpdesk.ts:105` — `GET /helpdesk/tickets/${ticketId}`
- **Backend:** `backend/helpdesk/router.py:109` — `GET /helpdesk/{ticket_id}`
- **Impact:** Ticket detail view returns 404.
- **Fix:** Change frontend to `GET /helpdesk/${ticketId}`.

### BUG-016: Helpdesk — Multiple endpoints use wrong URL prefix `/helpdesk/tickets/` vs `/helpdesk/`
- **Frontend:** `frontend/src/api/helpdesk.ts:100` — `GET /helpdesk/tickets` (list all), line 124 — `/helpdesk/tickets/{id}/comments`, line 135 — `/helpdesk/tickets/{id}/assign`, line 143 — `/helpdesk/tickets/{id}/escalate`, line 153 — `/helpdesk/tickets/{id}/status`
- **Backend:** All routes use `/helpdesk/` prefix: `GET /helpdesk/` (list), `POST /helpdesk/{id}/responses`, `PATCH /helpdesk/{id}`
- **Impact:** All list-all, comment, assign, escalate, and status change calls return 404.
- **Fix:** Remove `/tickets` from all frontend helpdesk API paths. Also:
  - Comments: Frontend sends to `/comments` but backend has `/responses` (body field mismatch too — frontend sends `content`, backend expects `body`)
  - Assign: No dedicated `/assign` endpoint — use `PATCH /helpdesk/{id}` with `assigned_to_id`
  - Escalate: No dedicated `/escalate` endpoint — must be added or use PATCH
  - Status: No dedicated `/status` endpoint — use `PATCH /helpdesk/{id}` with `status`

### BUG-017: Helpdesk — Frontend calls `GET /helpdesk/summary` but no summary endpoint exists
- **Frontend:** `frontend/src/api/helpdesk.ts:160` — `GET /helpdesk/summary`
- **Backend:** No matching route in `backend/helpdesk/router.py`
- **Impact:** Dashboard helpdesk widget returns 404.
- **Fix:** Add `GET /summary` endpoint in helpdesk router.

### BUG-018: Dashboard — Frontend calls `/dashboard/upcoming-birthdays` but backend has `/dashboard/birthdays`
- **Frontend:** `frontend/src/api/dashboard.ts:112` — `GET /dashboard/upcoming-birthdays`
- **Backend:** `backend/dashboard/router.py:65` — `GET /dashboard/birthdays`
- **Impact:** Upcoming birthdays widget on dashboard returns 404.
- **Fix:** Change frontend to `/dashboard/birthdays` or add alias route.

---

## 🟡 High — Wrong Data / Behavior

### BUG-019: Dashboard summary — Frontend expects `pending_approvals` but backend returns `pending_leave_requests`
- **Frontend:** `frontend/src/api/dashboard.ts:14` — interface has `pending_approvals`
- **Backend:** `backend/dashboard/schemas.py:27` — field is `pending_leave_requests`
- **Impact:** "Pending Approvals" card on dashboard always shows "—" (undefined).
- **Fix:** Align field names — either rename backend to `pending_approvals` or frontend to `pending_leave_requests`.

### BUG-020: Dashboard summary — Frontend expects `new_joiners_this_month` and `attrition_this_month` but backend doesn't return them
- **Frontend:** `frontend/src/api/dashboard.ts:15-16` — interface has `new_joiners_this_month`, `attrition_this_month`
- **Backend:** `backend/dashboard/schemas.py` — `DashboardSummaryResponse` has no such fields
- **Impact:** These values are silently undefined in the frontend.
- **Fix:** Add these fields to the backend `DashboardSummaryResponse` schema and compute them in `DashboardService.get_summary()`.

### BUG-021: Backend `main.py` — Duplicate imports
- **File:** `backend/main.py:22-27`
- **Issue:** `expenses_router`, `fnf_router`, `helpdesk_router`, and `salary_router` are imported twice each.
- **Impact:** Not a runtime error (Python deduplicates), but indicates copy-paste error and could mask actual import bugs.
- **Fix:** Remove duplicate import lines 22-28.

### BUG-022: Helpdesk — Frontend `Ticket` type fields don't match backend `TicketOut` schema
- **Frontend:** `frontend/src/api/helpdesk.ts:38-55` — uses `subject`, `description`, `reporter_id`, `reporter`, `assignee_id`, `assignee`, `comments`, `closed_at`
- **Backend:** `backend/helpdesk/schemas.py:46-63` — uses `title` (not `subject`), no `description` field, `raised_by_id`/`raised_by_name` (not `reporter`), `assigned_to_id`/`assigned_to_name` (not `assignee`), `responses` (not `comments`), no `closed_at`
- **Impact:** All ticket data renders incorrectly — subject shows blank, reporter name missing, comments section empty.
- **Fix:** Align frontend types with backend schema. Major field rename: `subject`→`title`, `description`→remove (or add to backend), `reporter`→`raised_by`, `assignee`→`assigned_to`, `comments`→`responses`, field names inside those objects differ too.

### BUG-023: Helpdesk — Frontend creates ticket with `subject`/`description` but backend expects `title`
- **Frontend:** `frontend/src/api/helpdesk.ts:109-115` — sends `{ subject, description, category, priority }`
- **Backend:** `backend/helpdesk/schemas.py:68-72` — `TicketCreate` expects `title`, not `subject`. No `description` field.
- **Impact:** Creating tickets sends wrong field name, backend will reject or store null title.
- **Fix:** Change frontend to send `title` instead of `subject`. Add `description` to backend `TicketCreate` if needed.

### BUG-024: Helpdesk — Comment field name mismatch: frontend sends `content`, backend expects `body`
- **Frontend:** `frontend/src/api/helpdesk.ts:124` — sends `{ content }`
- **Backend:** `backend/helpdesk/schemas.py:36` — `ResponseCreate` expects `body`
- **Impact:** Adding comments sends wrong field, backend will reject with validation error.
- **Fix:** Change frontend to send `{ body: content }` or add `content` alias in backend.

### BUG-025: Expenses — Frontend `ExpenseClaim` type fields don't match backend `ExpenseOut` schema
- **Frontend:** `frontend/src/api/expenses.ts:42-60` — uses `status`, `items`, `receipt_urls`, `reviewed_by`, `reviewer`, `reviewed_at`, `reviewer_remarks`, `reimbursed_at`, `category`, `total_amount`, `description`
- **Backend:** `backend/expenses/schemas.py:51-66` — uses `approval_status` (not `status`), no `items` field, no `receipt_urls`, no `reviewer` object, no `reimbursed_at`, no `category`, has `amount` (not `total_amount`), no `description`
- **Impact:** Expense status badges always show default, items/receipts never render, amount shows 0.
- **Fix:** Comprehensive field alignment needed. Key: `status`→`approval_status`, `total_amount`→`amount`, add missing fields to backend or adjust frontend.

### BUG-026: Expenses — Frontend create payload uses `total_amount` but backend expects `amount`
- **Frontend:** `frontend/src/api/expenses.ts:104-111` — sends `total_amount`, `category`, `description`, `receipt_urls`
- **Backend:** `backend/expenses/schemas.py:25-31` — `ExpenseCreate` expects `amount`, `currency`, `expenses`, `remarks` — no `total_amount`, no `category`, no `description`, no `receipt_urls`
- **Impact:** Creating expenses sends wrong fields, amount will be missing from request, backend will return 422 validation error.
- **Fix:** Align create payload: `total_amount`→`amount`, `description`→`remarks`.

### BUG-027: Attendance — `RegularizationRejectRequest` is imported but no reject endpoint exists
- **File:** `backend/attendance/router.py:21` — imports `RegularizationRejectRequest`
- **Issue:** The schema is imported and the service has `reject_regularization()` but no router endpoint exists.
- **Impact:** Managers/HR cannot reject regularization requests via API.
- **Fix:** Add `PUT /regularizations/{regularization_id}/reject` endpoint.

### BUG-028: Backend Salary schemas don't match frontend types at all
- **Frontend:** `SalarySlip` expects: `month`, `year`, `basic_salary`, `gross_earnings`, `total_deductions`, `net_salary`, `components[]`, `payment_status`, `days_worked`, `days_payable`, `loss_of_pay_days`
- **Backend:** `SalaryOut` has: `ctc`, `gross_pay`, `net_pay`, `earnings[]`, `deductions[]`, `contributions[]`, `effective_date`, `pay_period`, `is_current`
- **Impact:** Even if URLs matched, the data shapes are completely different — nothing would render correctly.
- **Fix:** Either redesign the backend salary system to support monthly slips, or redesign the frontend to work with CTC-based salary structure.

### BUG-029: Backend CTC breakdown schema doesn't match frontend `CTCBreakdown` type
- **Frontend:** `CTCBreakdown` expects: `annual_ctc`, `monthly_ctc`, `components[]` with `name`, `type`, `annual_amount`, `monthly_amount`, `percentage_of_ctc`
- **Backend:** `CTCBreakdownOut` has: `employee_id`, `employee_name`, `ctc`, `gross_pay`, `net_pay`, `earnings[]`, `deductions[]`, `contributions[]` (all `List[Any]`)
- **Impact:** CTC breakdown charts render empty — no structured component data.
- **Fix:** Update backend `get_ctc_breakdown()` to return structured component data matching frontend expectations.

### BUG-030: Admin routes — Sidebar links to `/admin/settings`, `/admin/roles`, `/admin/holidays` but no matching routes in `App.tsx`
- **Frontend:** `frontend/src/lib/constants.ts:31-33` — defines `SETTINGS: "/admin/settings"`, `ADMIN_ROLES: "/admin/roles"`, `ADMIN_HOLIDAYS: "/admin/holidays"`
- **Frontend:** `frontend/src/App.tsx` — no routes defined for `/admin/*`
- **Impact:** Clicking admin sidebar links shows 404 page. Only `SettingsPage.tsx` exists in `frontend/src/pages/admin/`.
- **Fix:** Add routes in `App.tsx`:
  ```tsx
  <Route path="admin/settings" element={<SettingsPage />} />
  <Route path="admin/roles" element={<RolesPage />} />
  <Route path="admin/holidays" element={<HolidaysPage />} />
  ```
  Create `RolesPage.tsx` and `HolidaysPage.tsx` or a combined admin page.

### BUG-031: Auth — `UserInfo` schema returns `department` as `str` but frontend `User` type expects `Department` object
- **Frontend:** `frontend/src/lib/types.ts:15-16` — `User.department: Department | null` (object with `id`, `name`)
- **Backend:** `backend/auth/schemas.py:30` — `UserInfo.department: str` (just the name)
- **Impact:** `TokenResponse` from `/auth/google` returns department as a string. Frontend code accessing `user.department.name` after Google login may crash.
- **Fix:** The `GET /me` endpoint returns `DeptBrief` object (correct), but the login response `TokenResponse.user` uses `UserInfo` which flattens to string. Unify to always return object.

### BUG-032: FnF — Backend routes exist (`/api/v1/fnf/*`) but no frontend page or API module
- **Backend:** `backend/fnf/router.py` — 4 endpoints registered
- **Frontend:** No `frontend/src/api/fnf.ts`, no FnF page, no sidebar link
- **Impact:** FnF settlement feature is invisible to users despite backend support.
- **Fix:** Add frontend API module and page, or remove from backend if not in scope.

---

## 🔵 Medium — UX Issues

### BUG-033: Notification bell is non-functional — no API integration
- **File:** `frontend/src/components/layout/Header.tsx:82-88`
- **Issue:** Bell icon is rendered with a hardcoded pulsing dot but doesn't fetch from `/api/v1/notifications/unread-count` and has no dropdown/panel.
- **Fix:** Create `frontend/src/api/notifications.ts`, add notification panel component, wire to bell icon.

### BUG-034: Profile button in header dropdown does nothing
- **File:** `frontend/src/components/layout/Header.tsx:126-131`
- **Issue:** "Profile" button closes dropdown but doesn't navigate anywhere.
- **Fix:** Navigate to `/employees/${user.id}` or a dedicated `/profile` page.

### BUG-035: Header `PAGE_TITLES` is incomplete — many pages show generic "HR Intelligence"
- **File:** `frontend/src/components/layout/Header.tsx:18-26`
- **Issue:** Only 7 pages defined. Missing: Org Chart, Departments, Leave Calendar, Salary, Helpdesk, Expenses, Team Leave.
- **Fix:** Add all page paths to `PAGE_TITLES` map.

### BUG-036: `BottomNav` component referenced in `AppShell.tsx` but behavior/routes unknown
- **File:** `frontend/src/components/layout/AppShell.tsx:7`
- **Impact:** Mobile bottom navigation may link to wrong routes or be incomplete.
- **Fix:** Verify `BottomNav` links match current route structure.

### BUG-037: Helpdesk page shows `ticket.comments.length` but backend returns `responses`
- **File:** `frontend/src/pages/HelpdeskPage.tsx:264`
- **Issue:** `ticket.comments.length` will be undefined because backend returns `responses[]` field.
- **Impact:** Comment count always shows 0, and the comments section is empty.
- **Fix:** Map `responses` → `comments` in the API layer or update component to use `responses`.

### BUG-038: Expenses — Frontend `ExpenseClaim` has no `category` field coming from backend
- **File:** `frontend/src/pages/ExpensesPage.tsx:243`
- **Issue:** `claim.category` is used for category emoji/label but backend `ExpenseOut` has no `category` field.
- **Impact:** Category labels/emojis never render — falls back to "Miscellaneous" for everything.
- **Fix:** Add `category` field to backend `expense_claims` table and `ExpenseOut` schema.

### BUG-039: Helpdesk — `TicketCard` accesses `ticket.subject` and `ticket.description` but backend returns `ticket.title`
- **File:** `frontend/src/pages/HelpdeskPage.tsx:247-252`
- **Issue:** `ticket.subject` → undefined (backend sends `title`), `ticket.description` → undefined (no such field).
- **Impact:** Ticket cards show blank titles and descriptions.
- **Fix:** Use `ticket.title` for display, add description to backend or remove from frontend.

### BUG-040: Helpdesk — `TicketCard` accesses `ticket.assignee.display_name` but backend has `assigned_to_name` (string, not object)
- **File:** `frontend/src/pages/HelpdeskPage.tsx:258-263`
- **Issue:** Backend returns `assigned_to_name: str` not `assignee: { display_name }`.
- **Impact:** Assignee name never renders in ticket cards.
- **Fix:** Use `ticket.assigned_to_name` or enrich backend response with embedded object.

### BUG-041: Helpdesk — `TicketComment` type expects `author: EmployeeBrief` but backend `ResponseOut` has `author_name: str`
- **File:** `frontend/src/api/helpdesk.ts:30-31` vs `backend/helpdesk/schemas.py:29`
- **Issue:** Frontend expects nested `author.display_name`, backend sends flat `author_name`.
- **Impact:** Comment author names show "Unknown" in the chat thread.
- **Fix:** Use `author_name` directly or enrich backend response.

### BUG-042: Helpdesk — `TicketComment` expects `content` field but backend `ResponseOut` uses `body`
- **File:** Frontend type: `content: string` | Backend schema: `body: str`
- **Impact:** Comment text renders blank in the ticket detail view.
- **Fix:** Align field names.

---

## ⚪ Low — Cosmetic / Cleanup

### BUG-043: Backend `main.py` — App description says "Phase 1: Core HR + Attendance + Leave" but includes salary, helpdesk, expenses, FnF
- **File:** `backend/main.py:46`
- **Fix:** Update description to reflect v2 scope.

### BUG-044: Backend `main.py` — App version hardcoded as "1.0.0" in two places
- **File:** `backend/main.py:47,75`
- **Fix:** Use a shared constant or config; update to "2.0.0".

### BUG-045: Frontend `lib/types.ts` — `Department.id` and `Location.id` typed as `number` but backend uses UUID
- **File:** `frontend/src/lib/types.ts:3,8` — `id: number`
- **Backend:** `backend/auth/schemas.py:36,41` — `id: uuid.UUID`
- **Impact:** TypeScript type safety compromised but JS doesn't enforce at runtime.
- **Fix:** Change to `id: string` in types.ts.

### BUG-046: Frontend `PaginationMeta` duplicated across 5+ API files
- **Files:** `leave.ts`, `attendance.ts`, `helpdesk.ts`, `expenses.ts`, `employees.ts`, `lib/types.ts`
- **Fix:** Export from one shared location (`lib/types.ts`) and import everywhere.

### BUG-047: Backend helpdesk `TicketListResponse` returns flat `total/page/page_size` but frontend expects `meta` object
- **Backend:** `backend/helpdesk/schemas.py:76-79` — returns `{ data, total, page, page_size }`
- **Frontend:** `frontend/src/api/helpdesk.ts:68-70` — expects `{ data, meta: { page, page_size, total, total_pages, has_next, has_prev } }`
- **Impact:** Pagination controls break — `ticketsData.meta.total_pages` is undefined.
- **Fix:** Backend needs to return nested `meta` object with computed `total_pages`, `has_next`, `has_prev`, or frontend needs a transform layer. Same issue exists for `ExpenseListResponse` and `SalaryListResponse`.

### BUG-048: Backend expense `ExpenseListResponse` returns flat pagination but frontend expects `meta` object
- **Backend:** `backend/expenses/schemas.py:76-79` — `{ data, total, page, page_size }`
- **Frontend:** `frontend/src/api/expenses.ts:65-70` — expects `{ data, meta: { ... } }`
- **Impact:** Expense list pagination is completely broken.
- **Fix:** Same as BUG-047 — add nested `meta` or transform.

---

## Quick-Fix Priority Order

1. **Helpdesk API URLs + field names** (BUG-014 through BUG-017, BUG-022 through BUG-024) — entire helpdesk is broken
2. **Expenses API URLs + field names** (BUG-006 through BUG-013, BUG-025, BUG-026) — entire expenses module is broken
3. **Salary API URLs + schema mismatch** (BUG-001 through BUG-005, BUG-028, BUG-029) — entire salary module is broken
4. **Dashboard field mismatches** (BUG-018 through BUG-020) — dashboard widgets broken
5. **Admin routes** (BUG-030) — admin section inaccessible
6. **Missing regularization reject** (BUG-027) — approval workflow incomplete
7. **Pagination format** (BUG-047, BUG-048) — list views have broken pagination

---

## Root Cause Analysis

The frontend and backend appear to have been developed in parallel with an assumed API contract that was never fully synchronized. The three new modules (salary, helpdesk, expenses) have **zero** correct API paths — every single frontend call uses a different URL structure than the backend provides.

**Pattern observed:**
- Frontend assumes REST-style nested resources (`/helpdesk/tickets/{id}/comments`)
- Backend uses flat resources under the module prefix (`/helpdesk/{id}/responses`)
- Frontend assumes dedicated endpoints (`/my-claims`, `/team-claims`, `/summary`)
- Backend uses generic endpoints with query filters (`/`, `/?employee_id=...`)
- Frontend types assume rich nested objects (`reporter: EmployeeBrief`)
- Backend returns flat strings (`raised_by_name: str`)
