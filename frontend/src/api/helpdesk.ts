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
import type { PaginationMeta } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────

export type TicketStatus = "open" | "in_progress" | "resolved" | "closed";
export type TicketPriority = "low" | "medium" | "high" | "critical" | "urgent";
export type TicketCategory =
  | "it_support"
  | "hr_query"
  | "payroll"
  | "facilities"
  | "access_request"
  | "other";

/** Backend ResponseOut schema */
export interface TicketResponse {
  id: string;
  ticket_id: string;
  author_id: string | null;
  author_name: string | null;
  body: string;
  is_internal: boolean;
  created_at: string;
}

/** Keep TicketComment as alias for backward compat in pages */
export type TicketComment = TicketResponse;

/** Backend TicketOut schema */
export interface Ticket {
  id: string;
  ticket_number: string | null;
  title: string;
  category: string | null;
  status: TicketStatus;
  priority: TicketPriority;
  raised_by_id: string | null;
  raised_by_name: string | null;
  assigned_to_id: string | null;
  assigned_to_name: string | null;
  requested_on: string | null;
  resolved_at: string | null;
  created_at: string | null;
  updated_at: string | null;
  responses: TicketResponse[];
}

export interface TicketListResponse {
  data: Ticket[];
  meta: PaginationMeta;
}

// ── Helpers ────────────────────────────────────────────────────────

/** Normalize flat pagination to nested meta if backend returns flat format */
function normalizeTicketList(raw: any): TicketListResponse {
  if (raw.meta) return raw;
  const total = raw.total ?? 0;
  const page = raw.page ?? 1;
  const page_size = raw.page_size ?? 50;
  const total_pages = Math.max(1, Math.ceil(total / page_size));
  return {
    data: raw.data ?? [],
    meta: {
      page,
      page_size,
      total,
      total_pages,
      has_next: page < total_pages,
      has_prev: page > 1,
    },
  };
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
  return normalizeTicketList(data);
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
  return normalizeTicketList(data);
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
  title: string;
  category: TicketCategory;
  priority: TicketPriority;
}): Promise<Ticket> {
  const { data } = await apiClient.post("/helpdesk/", body);
  return data;
}

/** POST /helpdesk/{id}/responses — add a response/comment */
export async function addComment(
  ticketId: string,
  body: { body: string; is_internal?: boolean },
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
    assigned_to_id?: string;
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
