"use client";

import * as React from "react";

import { runEventsUrl } from "@/lib/api";
import type { BlogRunStatus, Plan, RunEventName } from "@/lib/types";

/**
 * Live pipeline state, derived from the backend SSE stream.
 *
 * Wire format (see backend/app/api/events.py): each message is
 *   event: <name>
 *   data: { "data": { ...payload }, "created_at": <float> }
 * so the useful payload lives under `parsed.data`.
 *
 * Emitted event names + payloads (backend graph.py / runner.py / quality_evaluator.py):
 *   status          { status, snapshot?, progress_step?, warnings_count?, resumed? }
 *   node_started    { node, iter?, sections? }
 *   node_completed  { node, mode?, needs_research?, evidence_count?, section_count?,
 *                     blog_title?, task_id?, title?, score?, issues_count?,
 *                     hallucinations_count?, sections_to_redo?, improved?, recovered? }
 *   section         { task_id, title }
 *   warning         { message }
 *   awaiting_input  { type: "plan_approval", plan }
 *   done            { status }
 *   error           { reason }
 */

export type NodeName =
  | "router"
  | "research"
  | "planner"
  | "writer"
  | "reducer"
  | "citation_guard"
  | "quality_eval";

export type NodeStatus = "pending" | "active" | "done" | "skipped" | "error";

export interface NodeState {
  name: NodeName;
  status: NodeStatus;
  startedAt?: number;
  endedAt?: number;
  /** Short live subtitle, e.g. "open_book · 4 sources" or "7 sections". */
  detail?: string;
}

export interface SectionChip {
  taskId: number | null;
  title: string | null;
  done: boolean;
}

export interface RunEventsState {
  /** Connection lifecycle for the EventSource itself. */
  connection: "connecting" | "open" | "closed";
  /** Latest run status seen on the stream (drives the right-pane view). */
  status: BlogRunStatus | null;
  nodes: NodeState[];
  /** Writers fanout: one chip per planned section as `section` events arrive. */
  sections: SectionChip[];
  /** Total planned sections (from planner's section_count), for "N / M drafted". */
  plannedSectionCount: number | null;
  warnings: string[];
  /** Latest quality score (0–10) if the evaluator has reported. */
  qualityScore: number | null;
  qualityIter: number | null;
  /** Set when the graph pauses for HITL plan approval. */
  awaitingPlan: Plan | null;
  blogTitle: string | null;
  mode: string | null;
  error: string | null;
  /** True once `done` or `error` (terminal) has been received. */
  finished: boolean;
}

const NODE_ORDER: NodeName[] = [
  "router",
  "research",
  "planner",
  "writer",
  "reducer",
  "citation_guard",
  "quality_eval",
];

function initialNodes(): NodeState[] {
  return NODE_ORDER.map((name) => ({ name, status: "pending" }));
}

function initialState(): RunEventsState {
  return {
    connection: "connecting",
    status: null,
    nodes: initialNodes(),
    sections: [],
    plannedSectionCount: null,
    warnings: [],
    qualityScore: null,
    qualityIter: null,
    awaitingPlan: null,
    blogTitle: null,
    mode: null,
    error: null,
    finished: false,
  };
}

type Payload = Record<string, unknown>;

type Action =
  | { type: "connection"; value: RunEventsState["connection"] }
  | { type: "event"; name: RunEventName; data: Payload; at: number }
  | { type: "reset" };

function setNode(
  nodes: NodeState[],
  name: NodeName,
  patch: Partial<NodeState>,
): NodeState[] {
  return nodes.map((n) => (n.name === name ? { ...n, ...patch } : n));
}

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}
function num(v: unknown): number | undefined {
  return typeof v === "number" ? v : undefined;
}

function reducer(state: RunEventsState, action: Action): RunEventsState {
  if (action.type === "reset") return initialState();
  if (action.type === "connection") {
    return { ...state, connection: action.value };
  }

  const { name, data, at } = action;

  switch (name) {
    case "status": {
      const status = str(data.status);
      const snapshot = (data.snapshot as Payload | undefined) ?? undefined;
      const next = { ...state };

      // "subscribed" carries a DB snapshot for late joiners.
      if (status === "subscribed" && snapshot) {
        next.status = (str(snapshot.status) as BlogRunStatus) ?? next.status;
        next.mode = str(snapshot.mode) ?? next.mode;
        next.blogTitle = str(snapshot.blog_title) ?? next.blogTitle;
        if (snapshot.plan && typeof snapshot.plan === "object") {
          next.awaitingPlan = snapshot.plan as Plan;
        }
        return next;
      }

      if (status) next.status = status as BlogRunStatus;
      const redoCount = num(data.warnings_count);
      if (redoCount !== undefined && redoCount === 0) {
        // keep as-is; warnings list is authoritative via `warning` events
      }
      return next;
    }

    case "node_started": {
      const node = str(data.node) as NodeName | undefined;
      if (!node || !NODE_ORDER.includes(node)) return state;
      const iter = num(data.iter);
      return {
        ...state,
        nodes: setNode(state.nodes, node, {
          status: "active",
          startedAt: at,
          detail:
            node === "quality_eval" && iter !== undefined
              ? `evaluating${iter > 0 ? ` · pass ${iter}` : ""}`
              : undefined,
        }),
      };
    }

    case "node_completed": {
      const node = str(data.node) as NodeName | undefined;
      // Synthetic nodes ("improvement", "retry") aren't in the visible pipeline.
      if (!node || !NODE_ORDER.includes(node)) return state;

      let detail: string | undefined;
      const patch: Partial<RunEventsState> = {};

      if (node === "router") {
        const mode = str(data.mode);
        const needsResearch = data.needs_research === true;
        detail = mode
          ? `${mode}${needsResearch ? " · researching" : " · closed-book"}`
          : undefined;
        if (mode) patch.mode = mode;
        // Router decided no research → mark research skipped.
        if (data.needs_research === false) {
          patch.nodes = setNode(state.nodes, "research", { status: "skipped" });
        }
      } else if (node === "research") {
        const n = num(data.evidence_count);
        detail = n !== undefined ? `${n} source${n === 1 ? "" : "s"}` : undefined;
      } else if (node === "planner") {
        const n = num(data.section_count);
        const title = str(data.blog_title);
        detail = n !== undefined ? `${n} section${n === 1 ? "" : "s"}` : undefined;
        if (n !== undefined) patch.plannedSectionCount = n;
        if (title) patch.blogTitle = title;
      } else if (node === "reducer") {
        detail = "assembled";
      } else if (node === "citation_guard") {
        detail = "checked";
      } else if (node === "quality_eval") {
        const score = num(data.score);
        const iter = num(data.iter);
        if (score !== undefined) {
          patch.qualityScore = score;
          detail = `score ${score.toFixed(1)}`;
        }
        if (iter !== undefined) patch.qualityIter = iter;
      }

      const nodes = setNode(patch.nodes ?? state.nodes, node, {
        status: "done",
        endedAt: at,
        detail,
      });

      return { ...state, ...patch, nodes };
    }

    case "section": {
      const taskId = num(data.task_id) ?? null;
      const title = str(data.title) ?? null;
      // Mark the writer node active if it isn't already done.
      const nodes = state.nodes.map((n) =>
        n.name === "writer" && n.status === "pending"
          ? { ...n, status: "active" as NodeStatus, startedAt: at }
          : n,
      );
      const sections: SectionChip[] = [
        ...state.sections,
        { taskId, title, done: true },
      ];
      const writerDetail = state.plannedSectionCount
        ? `${sections.length} / ${state.plannedSectionCount} drafted`
        : `${sections.length} drafted`;
      return {
        ...state,
        sections,
        nodes: nodes.map((n) =>
          n.name === "writer" ? { ...n, detail: writerDetail } : n,
        ),
      };
    }

    case "warning": {
      const message = str(data.message);
      if (!message) return state;
      return { ...state, warnings: [...state.warnings, message] };
    }

    case "awaiting_input": {
      if (str(data.type) === "plan_approval" && data.plan) {
        return {
          ...state,
          status: "awaiting_approval",
          awaitingPlan: data.plan as Plan,
        };
      }
      return state;
    }

    case "done": {
      const status = str(data.status) as BlogRunStatus | undefined;
      return {
        ...state,
        status: status ?? state.status,
        finished: true,
        connection: "closed",
      };
    }

    case "error": {
      const reason = str(data.reason);
      return {
        ...state,
        status: "failed",
        error: reason ?? "Run failed",
        finished: true,
        connection: "closed",
      };
    }

    default:
      return state;
  }
}

const EVENT_NAMES: RunEventName[] = [
  "status",
  "node_started",
  "node_completed",
  "section",
  "warning",
  "awaiting_input",
  "done",
  "error",
];

/**
 * Subscribe to a run's SSE stream and return a normalized timeline state.
 * Closes the EventSource on `done`/`error` and on unmount. The browser
 * auto-reconnects on transient errors while the run is still live.
 */
export function useRunEvents(
  runId: string | null,
  enabled = true,
): RunEventsState {
  const [state, dispatch] = React.useReducer(reducer, undefined, initialState);

  React.useEffect(() => {
    if (!runId || !enabled) return;

    dispatch({ type: "reset" });
    const es = new EventSource(runEventsUrl(runId));
    let closed = false;

    const close = () => {
      if (!closed) {
        closed = true;
        es.close();
      }
    };

    es.onopen = () => dispatch({ type: "connection", value: "open" });

    const handle = (name: RunEventName) => (ev: MessageEvent) => {
      let data: Payload = {};
      try {
        const parsed = JSON.parse(ev.data);
        data = (parsed?.data ?? parsed) as Payload;
      } catch {
        data = {};
      }
      dispatch({ type: "event", name, data, at: Date.now() });
      if (name === "done" || name === "error") close();
    };

    const listeners = EVENT_NAMES.map((name) => {
      const fn = handle(name);
      es.addEventListener(name, fn as EventListener);
      return [name, fn] as const;
    });

    es.onerror = () => {
      // If the run already ended, the server closed us — don't thrash reconnecting.
      if (es.readyState === EventSource.CLOSED) {
        dispatch({ type: "connection", value: "closed" });
      }
    };

    return () => {
      listeners.forEach(([name, fn]) =>
        es.removeEventListener(name, fn as EventListener),
      );
      close();
    };
  }, [runId, enabled]);

  return state;
}
