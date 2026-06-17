"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  FileText,
  Loader2,
  Minus,
  Network,
  PencilLine,
  Search,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { formatDuration, humanizeToken } from "@/lib/format";
import type {
  NodeName,
  NodeState,
  NodeStatus,
  RunEventsState,
} from "@/lib/use-run-events";
import { cn } from "@/lib/utils";

const NODE_META: Record<
  NodeName,
  { label: string; icon: LucideIcon; step: string }
> = {
  router: { label: "Router", icon: Network, step: "route" },
  research: { label: "Research", icon: Search, step: "search" },
  planner: { label: "Planner", icon: FileText, step: "plan" },
  writer: { label: "Writers", icon: PencilLine, step: "draft" },
  reducer: { label: "Reducer", icon: FileText, step: "merge" },
  citation_guard: { label: "Citation Guard", icon: ShieldCheck, step: "verify" },
  quality_eval: { label: "Quality", icon: Sparkles, step: "polish" },
};

const NODE_ORDER: NodeName[] = [
  "router",
  "research",
  "planner",
  "writer",
  "reducer",
  "citation_guard",
  "quality_eval",
];

const STEP_TO_NODE: Record<string, NodeName> = {
  running: "router",
  router: "router",
  research: "research",
  planner: "planner",
  awaiting_plan_approval: "planner",
  writer: "writer",
  reducer: "reducer",
  citation_guard: "citation_guard",
  quality_eval: "quality_eval",
};

function statusIcon(status: NodeStatus, active: boolean) {
  if (status === "done") return CheckCircle2;
  if (status === "skipped") return Minus;
  if (status === "error") return XCircle;
  if (status === "active" || active) return Loader2;
  return Circle;
}

function hasStreamProgress(nodes: NodeState[]) {
  return nodes.some(
    (node) =>
      node.status !== "pending" ||
      node.startedAt !== undefined ||
      node.detail !== undefined,
  );
}

function inferNodes(
  nodes: NodeState[],
  status?: string | null,
  progressStep?: string | null,
) {
  if (hasStreamProgress(nodes)) return nodes;

  if (status === "completed" || status === "completed_with_warnings") {
    return nodes.map((node) => ({ ...node, status: "done" as NodeStatus }));
  }

  const current = STEP_TO_NODE[progressStep || ""] ?? "router";
  const currentIndex = NODE_ORDER.indexOf(current);

  return nodes.map((node, index) => {
    if (index < currentIndex) return { ...node, status: "done" as NodeStatus };
    if (index === currentIndex) {
      if (status === "failed") return { ...node, status: "error" as NodeStatus };
      if (status === "awaiting_approval") {
        return {
          ...node,
          status: "active" as NodeStatus,
          detail: "waiting for review",
        };
      }
      if (status === "running" || status === "queued") {
        return { ...node, status: "active" as NodeStatus };
      }
    }
    return node;
  });
}

function nodeDuration(node: NodeState, now: number) {
  if (!node.startedAt) return null;
  const ended = node.endedAt ?? (node.status === "active" ? now : undefined);
  if (!ended) return null;
  return formatDuration(Math.max(0, ended - node.startedAt));
}

export function RunProgress({
  state,
  initialStatus,
  initialStep,
  initialMode,
  className,
}: {
  state: RunEventsState;
  initialStatus?: string | null;
  initialStep?: string | null;
  initialMode?: string | null;
  className?: string;
}) {
  const [now, setNow] = useState(() => Date.now());
  const status = state.status ?? initialStatus;
  const nodes = inferNodes(state.nodes, status, initialStep);
  const hasActiveNode = nodes.some((node) => node.status === "active");

  useEffect(() => {
    if (!hasActiveNode) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [hasActiveNode]);

  return (
    <div className={cn("border bg-card/70 p-5", className)}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-foreground">Pipeline</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {state.connection === "open"
              ? "Live stream connected"
              : state.finished
                ? "Stream closed"
                : "Connecting to stream"}
          </p>
        </div>
        <span className="font-mono text-xs uppercase tracking-normal text-muted-foreground">
          {humanizeToken(state.mode || initialMode) || "pending"}
        </span>
      </div>

      <ol className="mt-6 space-y-0">
        {nodes.map((node, index) => {
          const meta = NODE_META[node.name];
          const active = node.status === "active";
          const StepIcon = meta.icon;
          const StatusIcon = statusIcon(node.status, active);
          const duration = nodeDuration(node, now);
          const isLast = index === nodes.length - 1;
          const connectorFilled = node.status === "done" || node.status === "skipped";

          return (
            <li key={node.name} className="relative grid grid-cols-[2.5rem_1fr] gap-3">
              <div className="relative flex justify-center">
                <span
                  className={cn(
                    "z-10 flex size-9 items-center justify-center border bg-background",
                    node.status === "done" && "border-success/50 text-success",
                    node.status === "active" && "border-primary/70 text-primary",
                    node.status === "pending" && "border-border text-muted-foreground",
                    node.status === "skipped" && "border-muted text-muted-foreground",
                    node.status === "error" && "border-destructive/60 text-destructive",
                  )}
                >
                  <StatusIcon
                    className={cn("size-4", active && "animate-spin")}
                    aria-hidden="true"
                  />
                </span>
                {!isLast ? (
                  <span
                    className={cn(
                      "absolute top-9 h-full w-px bg-border",
                      connectorFilled && "bg-primary/60",
                    )}
                  />
                ) : null}
              </div>

              <div className="min-w-0 pb-6">
                <div className="flex min-h-9 flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <StepIcon className="size-4 text-primary" />
                    <span className="font-medium text-foreground">{meta.label}</span>
                    <span className="font-mono text-[11px] uppercase tracking-normal text-muted-foreground">
                      {meta.step}
                    </span>
                  </div>
                  {duration ? (
                    <span className="font-mono text-xs text-muted-foreground">
                      {duration}
                    </span>
                  ) : null}
                </div>
                {node.detail ? (
                  <p className="mt-1 break-words text-sm text-muted-foreground">{node.detail}</p>
                ) : null}

                {node.name === "writer" && state.sections.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {state.sections.map((section, sectionIndex) => (
                      <span
                        key={`${section.taskId ?? sectionIndex}-${sectionIndex}`}
                        className="inline-flex max-w-[14rem] min-w-0 items-center gap-1.5 border bg-background/60 px-2 py-1 text-xs text-muted-foreground"
                        title={section.title ?? undefined}
                      >
                        <CheckCircle2 className="size-3 shrink-0 text-success" />
                        <span className="truncate">
                          {section.title || `Section ${section.taskId ?? sectionIndex + 1}`}
                        </span>
                      </span>
                    ))}
                  </div>
                ) : null}

                {node.name === "quality_eval" && state.qualityScore !== null ? (
                  <div className="mt-3 inline-flex items-center gap-2 border border-primary/25 bg-primary/10 px-2.5 py-1 text-xs text-primary">
                    <Sparkles className="size-3.5" />
                    Score {state.qualityScore.toFixed(1)}
                    {state.qualityIter !== null ? ` / iter ${state.qualityIter}` : ""}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>

      {state.warnings.length ? (
        <div className="mt-2 border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
          <div className="flex items-center gap-2 font-medium">
            <AlertTriangle className="size-4" />
            {state.warnings.length} warning{state.warnings.length === 1 ? "" : "s"}
          </div>
        </div>
      ) : null}
    </div>
  );
}
