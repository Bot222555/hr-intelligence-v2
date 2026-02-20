/**
 * HelpdeskPage — Employee helpdesk / ticket system.
 *
 * Features:
 *  • Ticket list with status filters (Open, In Progress, Resolved, Closed)
 *  • Create new ticket form (category, priority, subject, description)
 *  • Ticket detail view with responses/comments thread
 *  • Assign to / escalate buttons for admins
 */

import { useCallback, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Ticket,
  Plus,
  X,
  Send,
  ChevronLeft,
  ChevronRight,
  AlertCircle,
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowUpRight,
  Filter,
  MessageCircle,
  User,
  Tag,
  Flag,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { cn, formatDate, getInitials } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { ADMIN_ROLES } from "@/lib/constants";
import * as helpdeskApi from "@/api/helpdesk";
import type {
  Ticket as TicketType,
  TicketStatus,
  TicketPriority,
  TicketCategory,
  TicketComment,
} from "@/api/helpdesk";

// ── Helpers ────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<
  TicketStatus,
  { label: string; bg: string; text: string; icon: typeof Clock; dot: string }
> = {
  open: {
    label: "Open",
    bg: "bg-blue-50 border-blue-200",
    text: "text-blue-700",
    icon: AlertCircle,
    dot: "bg-blue-500",
  },
  in_progress: {
    label: "In Progress",
    bg: "bg-amber-50 border-amber-200",
    text: "text-amber-700",
    icon: Clock,
    dot: "bg-amber-500",
  },
  resolved: {
    label: "Resolved",
    bg: "bg-emerald-50 border-emerald-200",
    text: "text-emerald-700",
    icon: CheckCircle2,
    dot: "bg-emerald-500",
  },
  closed: {
    label: "Closed",
    bg: "bg-slate-50 border-slate-200",
    text: "text-slate-600",
    icon: XCircle,
    dot: "bg-slate-400",
  },
};

const PRIORITY_CONFIG: Record<
  TicketPriority,
  { label: string; bg: string; text: string }
> = {
  low: { label: "Low", bg: "bg-slate-50 border-slate-200", text: "text-slate-600" },
  medium: { label: "Medium", bg: "bg-blue-50 border-blue-200", text: "text-blue-700" },
  high: { label: "High", bg: "bg-orange-50 border-orange-200", text: "text-orange-700" },
  urgent: { label: "Urgent", bg: "bg-red-50 border-red-200", text: "text-red-700" },
};

const CATEGORY_LABELS: Record<TicketCategory, string> = {
  it_support: "IT Support",
  hr_query: "HR Query",
  payroll: "Payroll",
  facilities: "Facilities",
  access_request: "Access Request",
  other: "Other",
};

const CATEGORY_EMOJI: Record<TicketCategory, string> = {
  it_support: "💻",
  hr_query: "👥",
  payroll: "💰",
  facilities: "🏢",
  access_request: "🔐",
  other: "📋",
};

function timeAgo(dateStr: string): string {
  const now = new Date();
  const then = new Date(dateStr);
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  if (diffDay === 1) return "yesterday";
  if (diffDay < 7) return `${diffDay}d ago`;
  return formatDate(dateStr);
}

// ── Component ──────────────────────────────────────────────────────

export function HelpdeskPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isAdmin =
    user && ADMIN_ROLES.includes(user.role as (typeof ADMIN_ROLES)[number]);

  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState<TicketStatus | "all">("all");
  const [selectedTicket, setSelectedTicket] = useState<TicketType | null>(null);
  const [page, setPage] = useState(1);

  // ── Queries ────────────────────────────────────────────────────

  const { data: ticketsData, isLoading: loadingTickets } = useQuery({
    queryKey: ["myTickets", statusFilter, page],
    queryFn: () =>
      helpdeskApi.getMyTickets({
        status: statusFilter === "all" ? undefined : statusFilter,
        page,
        page_size: 10,
      }),
  });

  const { data: ticketDetail, isLoading: loadingDetail } = useQuery({
    queryKey: ["ticketDetail", selectedTicket?.id],
    queryFn: () => helpdeskApi.getTicket(selectedTicket!.id),
    enabled: !!selectedTicket,
  });

  // ── Render ───────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-2xl font-bold text-foreground">Helpdesk</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Submit support tickets and track their resolution
          </p>
        </div>
        <Button
          onClick={() => {
            setShowForm(!showForm);
            if (showForm) setSelectedTicket(null);
          }}
          className="gap-2 shadow-md"
        >
          {showForm ? (
            <>
              <X className="h-4 w-4" /> Cancel
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> New Ticket
            </>
          )}
        </Button>
      </div>

      {/* Create Ticket Form */}
      {showForm && (
        <CreateTicketForm
          onSuccess={() => {
            setShowForm(false);
            queryClient.invalidateQueries({ queryKey: ["myTickets"] });
          }}
        />
      )}

      {/* Ticket Detail View */}
      {selectedTicket && !showForm && (
        <TicketDetailView
          ticket={ticketDetail || selectedTicket}
          isLoading={loadingDetail}
          isAdmin={!!isAdmin}
          onClose={() => setSelectedTicket(null)}
          onUpdate={() => {
            queryClient.invalidateQueries({ queryKey: ["ticketDetail", selectedTicket.id] });
            queryClient.invalidateQueries({ queryKey: ["myTickets"] });
          }}
        />
      )}

      {/* Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          My Tickets
        </h3>
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <div className="flex gap-1">
            {(["all", "open", "in_progress", "resolved", "closed"] as const).map(
              (s) => (
                <button
                  key={s}
                  onClick={() => {
                    setStatusFilter(s);
                    setPage(1);
                  }}
                  className={cn(
                    "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                    statusFilter === s
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground hover:bg-muted/80",
                  )}
                >
                  {s === "all" ? "All" : STATUS_CONFIG[s].label}
                </button>
              ),
            )}
          </div>
        </div>
      </div>

      {/* Ticket List */}
      {loadingTickets ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {ticketsData?.data.map((ticket) => (
              <TicketCard
                key={ticket.id}
                ticket={ticket}
                isSelected={selectedTicket?.id === ticket.id}
                onSelect={() =>
                  setSelectedTicket(
                    selectedTicket?.id === ticket.id ? null : ticket,
                  )
                }
              />
            ))}
            {ticketsData?.data.length === 0 && (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-16">
                  <Ticket className="h-12 w-12 text-muted-foreground/40" />
                  <p className="mt-3 text-sm text-muted-foreground">
                    No tickets found
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4 gap-2"
                    onClick={() => setShowForm(true)}
                  >
                    <Plus className="h-4 w-4" /> Create your first ticket
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Pagination */}
          {ticketsData && ticketsData.meta.total_pages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={!ticketsData.meta.has_prev}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" /> Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {ticketsData.meta.page} of {ticketsData.meta.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={!ticketsData.meta.has_next}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ── Ticket Card ────────────────────────────────────────────────────

function TicketCard({
  ticket,
  isSelected,
  onSelect,
}: {
  ticket: TicketType;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const statusCfg = STATUS_CONFIG[ticket.status];
  const priorityCfg = PRIORITY_CONFIG[ticket.priority];
  const StatusIcon = statusCfg.icon;

  return (
    <Card
      className={cn(
        "cursor-pointer transition-all hover:shadow-md",
        isSelected && "ring-2 ring-primary ring-offset-2",
      )}
      onClick={onSelect}
    >
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          {/* Left */}
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="mt-0.5 text-xl">
              {CATEGORY_EMOJI[ticket.category] || "📋"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-mono text-muted-foreground">
                  #{ticket.ticket_number}
                </span>
                <Badge className={cn("border text-xs", priorityCfg.bg, priorityCfg.text)}>
                  {priorityCfg.label}
                </Badge>
              </div>
              <p className="mt-1 font-semibold text-foreground line-clamp-1">
                {ticket.subject}
              </p>
              <p className="mt-0.5 text-sm text-muted-foreground line-clamp-2">
                {ticket.description}
              </p>
              <div className="mt-2 flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Tag className="h-3 w-3" />
                  {CATEGORY_LABELS[ticket.category]}
                </span>
                <span>·</span>
                <span>{timeAgo(ticket.created_at)}</span>
                {ticket.assignee && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <User className="h-3 w-3" />
                      {ticket.assignee.display_name || ticket.assignee.employee_code}
                    </span>
                  </>
                )}
                {ticket.comments.length > 0 && (
                  <>
                    <span>·</span>
                    <span className="flex items-center gap-1">
                      <MessageCircle className="h-3 w-3" />
                      {ticket.comments.length}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Right: status */}
          <Badge className={cn("gap-1 border text-xs shrink-0", statusCfg.bg, statusCfg.text)}>
            <StatusIcon className="h-3 w-3" />
            {statusCfg.label}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Create Ticket Form ─────────────────────────────────────────────

function CreateTicketForm({ onSuccess }: { onSuccess: () => void }) {
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<TicketCategory>("it_support");
  const [priority, setPriority] = useState<TicketPriority>("medium");
  const [error, setError] = useState<string | null>(null);

  const createMut = useMutation({
    mutationFn: helpdeskApi.createTicket,
    onSuccess: () => {
      setError(null);
      onSuccess();
    },
    onError: (err: any) => {
      setError(
        err?.response?.data?.detail || err?.message || "Failed to create ticket",
      );
    },
  });

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      setError(null);

      if (!subject.trim()) {
        setError("Please enter a subject");
        return;
      }
      if (!description.trim()) {
        setError("Please enter a description");
        return;
      }

      createMut.mutate({ subject, description, category, priority });
    },
    [subject, description, category, priority, createMut],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Ticket className="h-5 w-5 text-primary" />
          Create New Ticket
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid gap-5 sm:grid-cols-2">
            {/* Category */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                Category <span className="text-red-500">*</span>
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as TicketCategory)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {(Object.keys(CATEGORY_LABELS) as TicketCategory[]).map((cat) => (
                  <option key={cat} value={cat}>
                    {CATEGORY_EMOJI[cat]} {CATEGORY_LABELS[cat]}
                  </option>
                ))}
              </select>
            </div>

            {/* Priority */}
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-foreground">
                Priority <span className="text-red-500">*</span>
              </label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as TicketPriority)}
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {(Object.keys(PRIORITY_CONFIG) as TicketPriority[]).map((p) => (
                  <option key={p} value={p}>
                    {PRIORITY_CONFIG[p].label}
                  </option>
                ))}
              </select>
            </div>

            {/* Subject */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">
                Subject <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Brief summary of your issue..."
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            {/* Description */}
            <div className="space-y-1.5 sm:col-span-2">
              <label className="text-sm font-medium text-foreground">
                Description <span className="text-red-500">*</span>
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe your issue in detail. Include any relevant information, error messages, or steps to reproduce..."
                rows={5}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              />
            </div>
          </div>

          {/* Error */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          {/* Submit */}
          <div className="flex justify-end">
            <Button
              type="submit"
              disabled={createMut.isPending}
              className="gap-2 min-w-[160px]"
            >
              <Send className="h-4 w-4" />
              {createMut.isPending ? "Submitting…" : "Submit Ticket"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ── Ticket Detail View ─────────────────────────────────────────────

function TicketDetailView({
  ticket,
  isLoading,
  isAdmin,
  onClose,
  onUpdate,
}: {
  ticket: TicketType;
  isLoading: boolean;
  isAdmin: boolean;
  onClose: () => void;
  onUpdate: () => void;
}) {
  const [comment, setComment] = useState("");
  const [commentError, setCommentError] = useState<string | null>(null);
  const [showComments, setShowComments] = useState(true);

  const statusCfg = STATUS_CONFIG[ticket.status];
  const priorityCfg = PRIORITY_CONFIG[ticket.priority];

  const addCommentMut = useMutation({
    mutationFn: (content: string) =>
      helpdeskApi.addComment(ticket.id, { content }),
    onSuccess: () => {
      setComment("");
      setCommentError(null);
      onUpdate();
    },
    onError: (err: any) => {
      setCommentError(
        err?.response?.data?.detail || err?.message || "Failed to add comment",
      );
    },
  });

  const escalateMut = useMutation({
    mutationFn: () => helpdeskApi.escalateTicket(ticket.id),
    onSuccess: () => onUpdate(),
  });

  const statusMut = useMutation({
    mutationFn: (status: TicketStatus) =>
      helpdeskApi.updateTicketStatus(ticket.id, status),
    onSuccess: () => onUpdate(),
  });

  const handleAddComment = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!comment.trim()) return;
      addCommentMut.mutate(comment.trim());
    },
    [comment, addCommentMut],
  );

  return (
    <Card className="border-primary/20">
      <CardHeader className="flex-row items-start justify-between gap-4 pb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="text-xs font-mono text-muted-foreground">
              #{ticket.ticket_number}
            </span>
            <Badge className={cn("border text-xs", statusCfg.bg, statusCfg.text)}>
              {statusCfg.label}
            </Badge>
            <Badge className={cn("border text-xs", priorityCfg.bg, priorityCfg.text)}>
              <Flag className="mr-1 h-3 w-3" />
              {priorityCfg.label}
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {CATEGORY_EMOJI[ticket.category]} {CATEGORY_LABELS[ticket.category]}
            </Badge>
          </div>
          <CardTitle className="text-lg">{ticket.subject}</CardTitle>
          <CardDescription className="mt-2 whitespace-pre-wrap">
            {ticket.description}
          </CardDescription>
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
            <span>Created {formatDate(ticket.created_at)}</span>
            {ticket.assignee && (
              <>
                <span>·</span>
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  Assigned to {ticket.assignee.display_name || ticket.assignee.employee_code}
                </span>
              </>
            )}
            {ticket.resolved_at && (
              <>
                <span>·</span>
                <span>Resolved {formatDate(ticket.resolved_at)}</span>
              </>
            )}
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose}>
          ✕
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Admin actions */}
        {isAdmin && ticket.status !== "closed" && (
          <div className="flex items-center gap-2 rounded-lg border border-blue-200 bg-blue-50 p-3">
            <span className="text-sm font-medium text-blue-700">Admin actions:</span>
            <div className="flex flex-wrap gap-2">
              {ticket.status === "open" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => statusMut.mutate("in_progress")}
                  disabled={statusMut.isPending}
                >
                  Mark In Progress
                </Button>
              )}
              {(ticket.status === "open" || ticket.status === "in_progress") && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => statusMut.mutate("resolved")}
                    disabled={statusMut.isPending}
                  >
                    <CheckCircle2 className="mr-1 h-3 w-3" /> Resolve
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs border-orange-200 text-orange-700 hover:bg-orange-50"
                    onClick={() => escalateMut.mutate()}
                    disabled={escalateMut.isPending}
                  >
                    <ArrowUpRight className="mr-1 h-3 w-3" /> Escalate
                  </Button>
                </>
              )}
              {ticket.status === "resolved" && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => statusMut.mutate("closed")}
                  disabled={statusMut.isPending}
                >
                  Close Ticket
                </Button>
              )}
            </div>
          </div>
        )}

        {/* Comments thread */}
        <div>
          <button
            onClick={() => setShowComments(!showComments)}
            className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors"
          >
            <MessageCircle className="h-4 w-4" />
            Comments ({ticket.comments?.length || 0})
            {showComments ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>

          {showComments && (
            <div className="mt-3 space-y-3">
              {isLoading ? (
                <div className="flex justify-center py-6">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : ticket.comments?.length === 0 ? (
                <div className="rounded-lg border border-dashed p-6 text-center">
                  <MessageCircle className="mx-auto h-8 w-8 text-muted-foreground/40" />
                  <p className="mt-2 text-sm text-muted-foreground">
                    No comments yet. Be the first to respond.
                  </p>
                </div>
              ) : (
                ticket.comments?.map((c) => (
                  <CommentBubble key={c.id} comment={c} />
                ))
              )}

              {/* Add comment form */}
              {ticket.status !== "closed" && (
                <form onSubmit={handleAddComment} className="mt-4">
                  <div className="flex gap-2">
                    <textarea
                      value={comment}
                      onChange={(e) => setComment(e.target.value)}
                      placeholder="Write a comment..."
                      rows={2}
                      className="flex flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                    />
                    <Button
                      type="submit"
                      size="icon"
                      disabled={!comment.trim() || addCommentMut.isPending}
                      className="h-auto self-end"
                    >
                      {addCommentMut.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                  {commentError && (
                    <p className="mt-1 text-xs text-red-600">{commentError}</p>
                  )}
                </form>
              )}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Comment Bubble ─────────────────────────────────────────────────

function CommentBubble({ comment }: { comment: TicketComment }) {
  const authorName =
    comment.author?.display_name || comment.author?.employee_code || "Unknown";

  return (
    <div className="flex gap-3">
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback className="text-xs">
          {getInitials(authorName)}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-medium text-foreground">{authorName}</span>
          <span className="text-xs text-muted-foreground">{timeAgo(comment.created_at)}</span>
          {comment.is_internal && (
            <Badge variant="secondary" className="text-[10px]">
              Internal
            </Badge>
          )}
        </div>
        <div className="mt-1 rounded-lg rounded-tl-none border bg-muted/30 px-3 py-2">
          <p className="text-sm text-foreground whitespace-pre-wrap">
            {comment.content}
          </p>
        </div>
      </div>
    </div>
  );
}
