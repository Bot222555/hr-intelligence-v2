/**
 * Helpdesk API module — tickets, comments, assignments.
 *
 * All endpoints go through the authenticated apiClient.
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

export interface TicketComment {
  id: string;
  ticket_id: string;
  author_id: string;
  author: EmployeeBrief | null;
  content: string;
  is_internal: boolean;
  created_at: string;
}

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
  comments: TicketComment[];
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

export interface HelpdeskSummary {
  open_tickets: number;
  in_progress_tickets: number;
  resolved_today: number;
  avg_resolution_hours: number;
}

// ── API Calls ──────────────────────────────────────────────────────

export async function getMyTickets(params?: {
  status?: TicketStatus;
  category?: TicketCategory;
  page?: number;
  page_size?: number;
}): Promise<TicketListResponse> {
  const { data } = await apiClient.get("/helpdesk/my-tickets", { params });
  return data;
}

export async function getAllTickets(params?: {
  status?: TicketStatus;
  category?: TicketCategory;
  priority?: TicketPriority;
  assignee_id?: string;
  page?: number;
  page_size?: number;
}): Promise<TicketListResponse> {
  const { data } = await apiClient.get("/helpdesk/tickets", { params });
  return data;
}

export async function getTicket(ticketId: string): Promise<Ticket> {
  const { data } = await apiClient.get(`/helpdesk/tickets/${ticketId}`);
  return data;
}

export async function createTicket(body: {
  subject: string;
  description: string;
  category: TicketCategory;
  priority: TicketPriority;
}): Promise<Ticket> {
  const { data } = await apiClient.post("/helpdesk/tickets", body);
  return data;
}

export async function addComment(
  ticketId: string,
  body: { content: string; is_internal?: boolean },
): Promise<TicketComment> {
  const { data } = await apiClient.post(
    `/helpdesk/tickets/${ticketId}/comments`,
    body,
  );
  return data;
}

export async function assignTicket(
  ticketId: string,
  assigneeId: string,
): Promise<Ticket> {
  const { data } = await apiClient.put(
    `/helpdesk/tickets/${ticketId}/assign`,
    { assignee_id: assigneeId },
  );
  return data;
}

export async function escalateTicket(ticketId: string): Promise<Ticket> {
  const { data } = await apiClient.put(
    `/helpdesk/tickets/${ticketId}/escalate`,
  );
  return data;
}

export async function updateTicketStatus(
  ticketId: string,
  status: TicketStatus,
): Promise<Ticket> {
  const { data } = await apiClient.put(
    `/helpdesk/tickets/${ticketId}/status`,
    { status },
  );
  return data;
}

export async function getHelpdeskSummary(): Promise<HelpdeskSummary> {
  const { data } = await apiClient.get("/helpdesk/summary");
  return data;
}
