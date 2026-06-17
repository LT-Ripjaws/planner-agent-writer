import type {
  BlogRunCreate,
  BlogRunDetail,
  BlogRunResult,
  BlogRunSummary,
  PlanApprovalDecision,
} from "@/lib/types";

const DEFAULT_API_URL = "http://localhost:8000";

type ApiRequestInit = RequestInit & {
  next?: {
    revalidate?: number | false;
    tags?: string[];
  };
};

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function getApiBaseUrl() {
  return (process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
}

async function parseResponse(response: Response) {
  // 204 No Content (e.g. a successful DELETE) carries no body — and FastAPI
  // still sets `content-type: application/json` on it, so naively calling
  // `response.json()` throws on the empty body and turns a successful delete
  // into a spurious error. Read the body once and parse defensively.
  if (response.status === 204) return null;

  const text = await response.text();
  if (!text) return null;

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  }

  return text;
}

function detailFromBody(body: unknown, status: number) {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (
            typeof item === "object" &&
            item !== null &&
            "msg" in item &&
            typeof item.msg === "string"
          ) {
            return item.msg;
          }
          return String(item);
        })
        .join(" ");
    }
    return String(detail);
  }

  return `Request failed with status ${status}`;
}

async function apiRequest<TResponse>(
  path: string,
  init: ApiRequestInit = {},
): Promise<TResponse> {
  const headers = new Headers(init.headers);

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });
  const body = await parseResponse(response);

  if (!response.ok) {
    const detail = detailFromBody(body, response.status);
    throw new ApiError(detail, response.status, body);
  }

  return body as TResponse;
}

export function createRun(payload: BlogRunCreate) {
  return apiRequest<BlogRunSummary>("/api/blog-runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
}

export function listRuns(limit = 20, init?: ApiRequestInit) {
  const params = new URLSearchParams({ limit: String(limit) });

  return apiRequest<BlogRunSummary[]>(`/api/blog-runs?${params}`, init);
}

export function getRun(runId: string, init?: ApiRequestInit) {
  return apiRequest<BlogRunDetail>(`/api/blog-runs/${runId}`, init);
}

export function getResult(runId: string, init?: ApiRequestInit) {
  return apiRequest<BlogRunResult>(`/api/blog-runs/${runId}/result`, init);
}

export function deleteRun(runId: string) {
  return apiRequest<void>(`/api/blog-runs/${runId}`, {
    method: "DELETE",
  });
}

export function resumeRun(runId: string) {
  return apiRequest<BlogRunSummary>(`/api/blog-runs/${runId}/resume`, {
    method: "POST",
  });
}

export function approvePlan(runId: string, decision: PlanApprovalDecision) {
  return apiRequest<BlogRunSummary>(`/api/blog-runs/${runId}/approve-plan`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(decision),
  });
}

/** Absolute URL for the SSE stream (EventSource can't use the relative fetch wrapper). */
export function runEventsUrl(runId: string) {
  return `${getApiBaseUrl()}/api/blog-runs/${runId}/events`;
}
