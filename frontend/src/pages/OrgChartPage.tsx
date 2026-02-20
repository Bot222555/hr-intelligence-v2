/**
 * OrgChartPage — Interactive organisational hierarchy tree.
 *
 * Pure CSS tree layout — no D3 dependency.
 * Features: zoom/pan, collapse/expand nodes, click-to-navigate.
 */

import { useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  ChevronDown,
  ChevronRight,
  Users,
  Search,
  Loader2,
  AlertCircle,
  Network,
} from "lucide-react";
import { getOrgChart, type OrgChartNode } from "@/api/orgchart";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

// ── Zoom / Pan State ───────────────────────────────────────────────

function useZoomPan() {
  const [scale, setScale] = useState(0.85);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const isDragging = useRef(false);
  const lastPos = useRef({ x: 0, y: 0 });

  const zoomIn = () => setScale((s) => Math.min(s + 0.15, 2));
  const zoomOut = () => setScale((s) => Math.max(s - 0.15, 0.3));
  const resetView = () => {
    setScale(0.85);
    setTranslate({ x: 0, y: 0 });
  };

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true;
    lastPos.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current) return;
    const dx = e.clientX - lastPos.current.x;
    const dy = e.clientY - lastPos.current.y;
    lastPos.current = { x: e.clientX, y: e.clientY };
    setTranslate((t) => ({ x: t.x + dx, y: t.y + dy }));
  }, []);

  const onMouseUp = useCallback(() => {
    isDragging.current = false;
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.08 : 0.08;
    setScale((s) => Math.min(Math.max(s + delta, 0.3), 2));
  }, []);

  return {
    scale,
    translate,
    zoomIn,
    zoomOut,
    resetView,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onWheel,
  };
}

// ── Node Card ──────────────────────────────────────────────────────

function NodeCard({
  node,
  collapsedIds,
  toggleCollapse,
  searchTerm,
}: {
  node: OrgChartNode;
  collapsedIds: Set<string>;
  toggleCollapse: (id: string) => void;
  searchTerm: string;
}) {
  const navigate = useNavigate();
  const isCollapsed = collapsedIds.has(node.id);
  const hasChildren = node.children.length > 0;
  const initials = node.display_name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const isMatch =
    searchTerm &&
    (node.display_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (node.designation?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false) ||
      (node.department?.toLowerCase().includes(searchTerm.toLowerCase()) ?? false));

  return (
    <li className="relative flex flex-col items-center">
      {/* Card */}
      <div
        className={cn(
          "relative flex flex-col items-center gap-1 rounded-xl border bg-card px-4 py-3 shadow-sm transition-all hover:shadow-md cursor-pointer min-w-[180px] max-w-[220px]",
          isMatch && "ring-2 ring-primary ring-offset-2"
        )}
        onClick={(e) => {
          e.stopPropagation();
          navigate(`/employees?search=${encodeURIComponent(node.employee_code)}`);
        }}
      >
        {/* Photo / Avatar */}
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10 text-primary font-semibold text-sm overflow-hidden">
          {node.profile_photo_url ? (
            <img
              src={node.profile_photo_url}
              alt={node.display_name}
              className="h-full w-full object-cover rounded-full"
            />
          ) : (
            initials
          )}
        </div>

        {/* Name */}
        <span className="text-sm font-semibold text-foreground text-center leading-tight">
          {node.display_name}
        </span>

        {/* Designation */}
        {node.designation && (
          <span className="text-xs text-muted-foreground text-center leading-tight">
            {node.designation}
          </span>
        )}

        {/* Department badge */}
        {node.department && (
          <span className="mt-0.5 inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            {node.department}
          </span>
        )}

        {/* Expand/Collapse toggle */}
        {hasChildren && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              toggleCollapse(node.id);
            }}
            className="absolute -bottom-3 left-1/2 -translate-x-1/2 flex h-6 w-6 items-center justify-center rounded-full border bg-background shadow-sm hover:bg-muted z-10"
          >
            {isCollapsed ? (
              <ChevronRight className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
              {node.children.length}
            </span>
          </button>
        )}
      </div>

      {/* Children tree */}
      {hasChildren && !isCollapsed && (
        <ul className="org-children flex gap-6 pt-8 relative">
          {node.children.map((child) => (
            <NodeCard
              key={child.id}
              node={child}
              collapsedIds={collapsedIds}
              toggleCollapse={toggleCollapse}
              searchTerm={searchTerm}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// ── Main Page ──────────────────────────────────────────────────────

export function OrgChartPage() {
  const {
    scale,
    translate,
    zoomIn,
    zoomOut,
    resetView,
    onMouseDown,
    onMouseMove,
    onMouseUp,
    onWheel,
  } = useZoomPan();

  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const toggleCollapse = useCallback((id: string) => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const {
    data: orgData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["org-chart"],
    queryFn: () => getOrgChart({ max_depth: 8 }),
  });

  // Count total nodes
  const countNodes = (nodes: OrgChartNode[]): number =>
    nodes.reduce((acc, n) => acc + 1 + countNodes(n.children), 0);

  const totalNodes = orgData?.data ? countNodes(orgData.data) : 0;

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b bg-background px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Network className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Organisation Chart</h1>
            <p className="text-sm text-muted-foreground">
              {totalNodes} team member{totalNodes !== 1 ? "s" : ""} across the org
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search people..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-56 pl-9"
            />
          </div>

          {/* Zoom controls */}
          <div className="flex items-center gap-1 rounded-lg border bg-background p-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={zoomOut} title="Zoom out">
              <ZoomOut className="h-4 w-4" />
            </Button>
            <span className="min-w-[3rem] text-center text-xs text-muted-foreground">
              {Math.round(scale * 100)}%
            </span>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={zoomIn} title="Zoom in">
              <ZoomIn className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={resetView} title="Reset view">
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Tree canvas */}
      <div
        ref={containerRef}
        className="flex-1 overflow-hidden bg-muted/30 cursor-grab active:cursor-grabbing"
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        onWheel={onWheel}
      >
        {isLoading && (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <span className="ml-3 text-muted-foreground">Loading organisation chart…</span>
          </div>
        )}

        {error && (
          <div className="flex h-full items-center justify-center">
            <AlertCircle className="h-6 w-6 text-destructive" />
            <span className="ml-2 text-destructive">Failed to load org chart</span>
          </div>
        )}

        {orgData && orgData.data.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center text-muted-foreground">
            <Users className="h-12 w-12 mb-3 opacity-40" />
            <p className="text-lg font-medium">No organisation data available</p>
            <p className="text-sm">Employee records need to be loaded first.</p>
          </div>
        )}

        {orgData && orgData.data.length > 0 && (
          <div
            className="inline-flex min-w-full min-h-full items-start justify-center p-12"
            style={{
              transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
              transformOrigin: "center top",
            }}
          >
            <ul className="org-tree flex gap-6">
              {orgData.data.map((root) => (
                <NodeCard
                  key={root.id}
                  node={root}
                  collapsedIds={collapsedIds}
                  toggleCollapse={toggleCollapse}
                  searchTerm={searchTerm}
                />
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* CSS for tree connectors */}
      <style>{`
        .org-tree, .org-children {
          position: relative;
        }
        .org-tree > li::before,
        .org-tree > li::after,
        .org-children > li::before,
        .org-children > li::after {
          content: '';
          position: absolute;
          top: 0;
        }
        /* vertical line from parent */
        .org-children > li::before {
          left: 50%;
          border-left: 2px solid hsl(var(--border));
          width: 0;
          height: 32px;
          top: 0;
        }
        /* horizontal line connecting siblings */
        .org-children > li::after {
          top: 0;
          height: 0;
          border-top: 2px solid hsl(var(--border));
        }
        .org-children > li:first-child::after {
          left: 50%;
          width: 50%;
        }
        .org-children > li:last-child::after {
          right: 50%;
          left: 0;
          width: 50%;
        }
        .org-children > li:only-child::after {
          display: none;
        }
        .org-children > li:not(:first-child):not(:last-child)::after {
          left: 0;
          width: 100%;
        }
        /* vertical line down from parent's collapse button */
        .org-children::before {
          content: '';
          position: absolute;
          left: 50%;
          top: -12px;
          border-left: 2px solid hsl(var(--border));
          height: 12px;
        }
      `}</style>
    </div>
  );
}
