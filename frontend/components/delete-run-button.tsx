"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ApiError, deleteRun } from "@/lib/api";
import { runsQueryKey } from "@/lib/use-runs";
import { Button } from "@/components/ui/button";

type DeleteRunButtonProps = {
  runId: string;
  title?: string | null;
  redirectToDashboard?: boolean;
  showLabel?: boolean;
  className?: string;
  size?: "sm" | "icon";
  variant?: "destructive" | "ghost" | "secondary";
};

function deleteErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Could not delete this run.";
}

function confirmMessage(title?: string | null) {
  if (!title) {
    return "Delete this run? This removes it from recent brews.";
  }

  const displayTitle = title.length > 80 ? `${title.slice(0, 77)}...` : title;
  return `Delete "${displayTitle}"? This removes it from recent brews.`;
}

export function DeleteRunButton({
  runId,
  title,
  redirectToDashboard = false,
  showLabel = false,
  className,
  size = showLabel ? "sm" : "icon",
  variant = showLabel ? "destructive" : "ghost",
}: DeleteRunButtonProps) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const mutation = useMutation({
    mutationFn: () => deleteRun(runId),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["run", runId] });
      queryClient.removeQueries({ queryKey: ["run-result", runId] });
      await queryClient.invalidateQueries({ queryKey: runsQueryKey(20) });
      toast.success("Run deleted");
      if (redirectToDashboard) {
        router.push("/dashboard");
      }
    },
    onError: (error) => toast.error(deleteErrorMessage(error)),
  });

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      disabled={mutation.isPending}
      aria-label="Delete run"
      title="Delete run"
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!window.confirm(confirmMessage(title))) return;
        mutation.mutate();
      }}
    >
      <Trash2 className="size-4" />
      {showLabel ? "Delete" : null}
    </Button>
  );
}
