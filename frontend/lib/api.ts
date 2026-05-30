import type {
  BlogRunCreate,
  BlogRunDetail,
  BlogRunResult,
  BlogRunSummary
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
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }

  return response.text();
}

async function apiRequest<TResponse>(
  path: string,
  init: ApiRequestInit = {}
): Promise<TResponse> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers
  });
  const body = await parseResponse(response);

  if (!response.ok) {
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Request failed with status ${response.status}`;

    throw new ApiError(detail, response.status, body);
  }

  return body as TResponse;
}

export function createRun(payload: BlogRunCreate) {
  return apiRequest<BlogRunSummary>("/api/blog-runs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
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
