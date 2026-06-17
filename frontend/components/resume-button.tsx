"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { ApiError, resumeRun } from "@/lib/api";
import { runsQueryKey } from "@/lib/use-runs";
import { Button } from "@/components/ui/button";

function resumeErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Could not resume the run. Check the backend connection.";
}

export function ResumeButton({
  runId,
  onResumed,
  size = "sm",
}: {
  runId: string;
  onResumed?: () => void;
  size?: "sm" | "default";
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => resumeRun(runId),
    onSuccess: async () => {
      toast.success("Run resumed");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: runsQueryKey(20) }),
        queryClient.invalidateQueries({ queryKey: ["run", runId] }),
      ]);
      onResumed?.();
    },
    onError: (error) => toast.error(resumeErrorMessage(error)),
  });

  return (
    <Button
      type="button"
      size={size}
      variant="secondary"
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      <RotateCcw className={mutation.isPending ? "size-4 animate-spin" : "size-4"} />
      Resume
    </Button>
  );
}
