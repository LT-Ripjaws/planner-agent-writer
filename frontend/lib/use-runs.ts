"use client";

import { useQuery } from "@tanstack/react-query";

import { listRuns } from "@/lib/api";
import type { BlogRunSummary } from "@/lib/types";

export const runsQueryKey = (limit = 20) => ["runs", limit] as const;

export function isLiveRun(run: BlogRunSummary) {
  return ["queued", "running", "awaiting_approval"].includes(run.status);
}

export function useRuns(limit = 20) {
  return useQuery({
    queryKey: runsQueryKey(limit),
    queryFn: () => listRuns(limit),
    refetchInterval: (query) => {
      const runs = query.state.data;
      return runs?.some(isLiveRun) ? 2500 : 8000;
    },
  });
}
