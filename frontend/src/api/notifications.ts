/**
 * Notifications API module.
 *
 * Backend routes:
 *   GET /notifications              — list notifications
 *   GET /notifications/unread-count — unread count
 *   PUT /notifications/{id}/read    — mark one as read
 *   PUT /notifications/read-all     — mark all as read
 */

import apiClient from "./client";
import type { PaginationMeta } from "@/lib/types";

// ── Types ──────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  employee_id: string;
  title: string;
  message: string;
  type: string;
  entity_type: string | null;
  entity_id: string | null;
  is_read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  data: Notification[];
  meta?: PaginationMeta;
}

export interface UnreadCountResponse {
  count: number;
}

// ── API Calls ──────────────────────────────────────────────────────

/** GET /notifications */
export async function getNotifications(params?: {
  is_read?: boolean;
  page?: number;
  page_size?: number;
}): Promise<NotificationListResponse> {
  const { data } = await apiClient.get("/notifications", { params });
  return data;
}

/** GET /notifications/unread-count */
export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const { data } = await apiClient.get("/notifications/unread-count");
  return data;
}

/** PUT /notifications/{id}/read */
export async function markAsRead(notificationId: string): Promise<Notification> {
  const { data } = await apiClient.put(`/notifications/${notificationId}/read`);
  return data;
}

/** PUT /notifications/read-all */
export async function markAllAsRead(): Promise<{ message: string }> {
  const { data } = await apiClient.put("/notifications/read-all");
  return data;
}
