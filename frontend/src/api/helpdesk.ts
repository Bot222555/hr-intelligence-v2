/**
 * Helpdesk API module — tickets, responses, status updates.
 *
 * All endpoints go through the authenticated apiClient.
 *
 * Backend routes:
 *   GET  /helpdesk/          — list all tickets
 *   GET  /helpdesk/my-tickets — current user's tickets
 *   GET  /helpdesk/{id}      — single ticket detail
 *   GET  /helpdesk/{id}/responses — ticket responses
 *   POST /helpdesk/          — create ticket
 *   POST /helpdesk/{id}/responses — add response
 *   PATCH /helpdesk/{id}     — update ticket (status, assignee, etc.)
 *   DELETE /helpdesk/{id}    — delete ticket
 */

import apiClient from "./client";

// ── Types ──────────────────────────────────────────────────────────

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "low" | "medium" | "high" | "urgent";
export type TicketCategory =
  | "it_support"
  | "hr_query"
  | "payroll"
  | "facilities"
  | "access_request"
  | "other";

export interface EmployeeBrief {
  id: string;
  employee_code: string;
  display_name: string | null;
  designation: string | null;
  department_name: string | null;
  profile_photo_url: string | null;
}

export interface TicketResponse {
  id: string;
  ticket_id: string;
  author_id: string;
  author: EmployeeBrief | null;
  content: string;
  is_internal: boolean;
  created_at: string;
}

/** Keep TicketComment as alias for backward compat in pages */
export type TicketComment = TicketResponse;

export interface Ticket {
  id: string;
  ticket_number: string;
  subject: string;
  description: string;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  reporter_id: string;
  reporter: EmployeeBrief | null;
  assignee_id: string | null;
  assignee: EmployeeBrief | null;
  comments: TicketResponse[];
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  closed_at: string | null;
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface TicketListResponse {
  data: Ticket[];
  meta: PaginationMeta;
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /helpdesk/my-tickets */
export async function getMyTickets(params?: {
  status?: TicketStatus;
  category?: TicketCategory;
  page?: number;
  page_size?: number;
}): Promise<TicketListResponse> {
  const { data } = await apiClient.get("/helpdesk/my-tickets", { params });
  return data;
}

/** GET /helpdesk/ — all tickets (admin/manager view) */
export async function getAllTickets(params?: {
  status?: TicketStatus;
  category?: TicketCategory;
  priority?: TicketPriority;
  assignee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<TicketListResponse> {
  const { data } = await apiClient.get("/helpdesk/", { params });
  return data;
}

/** GET /helpdesk/{id} */
export async function getTicket(ticketId: string): Promise<Ticket> {
  const { data } = await apiClient.get(`/helpdesk/${ticketId}`);
  return data;
}

/** GET /helpdesk/{id}/responses */
export async function getTicketResponses(ticketId: string): Promise<TicketResponse[]> {
  const { data } = await apiClient.get(`/helpdesk/${ticketId}/responses`);
  return data;
}

/** POST /helpdesk/ — create a new ticket */
export async function createTicket(body: {
  subject: string;
  description: string;
  category: TicketCategory;
  priority: TicketPriority;
}): Promise<Ticket> {
  const { data } = await apiClient.post("/helpdesk/", body);
  return data;
}

/** POST /helpdesk/{id}/responses — add a response/comment */
export async function addComment(
  ticketId: string,
  body: { content: string; is_internal?: boolean },
): Promise<TicketResponse> {
  const { data } = await apiClient.post(
    `/helpdesk/${ticketId}/responses`,
    body,
  );
  return data;
}

/** PATCH /helpdesk/{id} — update ticket fields (status, assignee, etc.) */
export async function updateTicket(
  ticketId: string,
  body: {
    status?: TicketStatus;
    assignee_id?: string;
    priority?: TicketPriority;
  },
): Promise<Ticket> {
  const { data } = await apiClient.patch(`/helpdesk/${ticketId}`, body);
  return data;
}

/**
 * Convenience: update just the status.
 * Uses PATCH /helpdesk/{id} under the hood.
 */
export async function updateTicketStatus(
  ticketId: string,
  status: TicketStatus,
): Promise<Ticket> {
  return updateTicket(ticketId, { status });
}

/** DELETE /helpdesk/{id} */
export async function deleteTicket(ticketId: string): Promise<void> {
  await apiClient.delete(`/helpdesk/${ticketId}`);
}
