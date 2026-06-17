"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, PencilLine, Send, XCircle } from "lucide-react";
import { toast } from "sonner";

import { ApiError, approvePlan } from "@/lib/api";
import type { Plan, PlannedBlogKind, Task } from "@/lib/types";
import { runsQueryKey } from "@/lib/use-runs";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type EditableTask = Task & {
  bulletText: string;
};

type EditablePlan = Omit<Plan, "tasks"> & {
  tasks: EditableTask[];
};

const blogKinds: PlannedBlogKind[] = [
  "explainer",
  "tutorial",
  "news_roundup",
  "comparison",
  "system_design",
];

function clonePlan(plan: Plan): EditablePlan {
  return {
    ...plan,
    constraints: [...(plan.constraints ?? [])],
    tasks: plan.tasks.map((task) => ({
      ...task,
      bullets: [...task.bullets],
      tags: [...(task.tags ?? [])],
      bulletText: task.bullets.join("\n"),
    })),
  };
}

function cleanPlan(plan: EditablePlan): Plan {
  return {
    ...plan,
    blog_title: plan.blog_title.trim(),
    audience: plan.audience.trim(),
    tone: plan.tone.trim() || "neutral",
    constraints: plan.constraints.map((item) => item.trim()).filter(Boolean),
    tasks: plan.tasks.map(({ bulletText, ...task }, index) => ({
      ...task,
      id: Number.isFinite(task.id) ? task.id : index + 1,
      title: task.title.trim(),
      goal: task.goal.trim(),
      bullets: bulletText
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      tags: task.tags.map((tag) => tag.trim()).filter(Boolean),
      target_words: Number(task.target_words),
      requires_research: Boolean(task.requires_research),
      requires_citations: Boolean(task.requires_citations),
      requires_code: Boolean(task.requires_code),
    })),
  };
}

function validatePlan(plan: Plan): string[] {
  const errors: string[] = [];
  if (!plan.blog_title) errors.push("Blog title is required.");
  if (!plan.audience) errors.push("Audience is required.");
  if (!blogKinds.includes(plan.blog_kind)) errors.push("Choose a concrete blog kind.");
  if (plan.tasks.length < 5 || plan.tasks.length > 9) {
    errors.push("Plan must contain 5 to 9 tasks.");
  }

  plan.tasks.forEach((task, index) => {
    const label = `Task ${index + 1}`;
    if (!task.title) errors.push(`${label} needs a title.`);
    if (!task.goal) errors.push(`${label} needs a goal.`);
    if (task.bullets.length < 3 || task.bullets.length > 6) {
      errors.push(`${label} needs 3 to 6 bullets.`);
    }
    if (task.target_words < 120 || task.target_words > 220) {
      errors.push(`${label} target words must be 120 to 220.`);
    }
  });

  return errors;
}

function mutationError(error: unknown) {
  if (error instanceof ApiError) return error.message;
  return "Could not send the plan decision.";
}

export function PlanReview({
  runId,
  plan,
  onResolved,
  className,
}: {
  runId: string;
  plan: Plan;
  onResolved?: () => void;
  className?: string;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<EditablePlan>(() => clonePlan(plan));
  const cleaned = useMemo(() => cleanPlan(draft), [draft]);
  const validation = useMemo(() => validatePlan(cleaned), [cleaned]);

  const mutation = useMutation({
    mutationFn: (decision: { action: "approve" | "reject"; plan?: Plan }) =>
      approvePlan(runId, decision),
    onSuccess: async (_, decision) => {
      toast.success(decision.action === "reject" ? "Plan rejected" : "Plan approved");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["run", runId] }),
        queryClient.invalidateQueries({ queryKey: runsQueryKey(20) }),
      ]);
      onResolved?.();
    },
    onError: (error) => toast.error(mutationError(error)),
  });

  function updateTask(index: number, patch: Partial<EditableTask>) {
    setDraft((current) => ({
      ...current,
      tasks: current.tasks.map((task, taskIndex) =>
        taskIndex === index ? { ...task, ...patch } : task,
      ),
    }));
  }

  function approve() {
    if (editing) {
      if (validation.length) {
        toast.error(validation[0]);
        return;
      }
      mutation.mutate({ action: "approve", plan: cleaned });
      return;
    }

    mutation.mutate({ action: "approve" });
  }

  return (
    <div
      className={cn(
        "border border-warning/35 bg-warning/10 p-5 text-foreground",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-warning">Plan review needed</p>
          {editing ? (
            <Input
              className="mt-3 max-w-2xl bg-background/70 font-serif text-2xl font-semibold"
              value={draft.blog_title}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  blog_title: event.target.value,
                }))
              }
            />
          ) : (
            <h2 className="mt-2 text-2xl font-semibold">{plan.blog_title}</h2>
          )}
          <p className="mt-2 text-sm text-muted-foreground">
            {plan.audience} / {plan.tone} / {plan.blog_kind.replace(/_/g, " ")}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={mutation.isPending}
            onClick={() => setEditing((value) => !value)}
          >
            <PencilLine className="size-4" />
            {editing ? "Preview" : "Edit plan"}
          </Button>
          <Button
            type="button"
            disabled={mutation.isPending || (editing && validation.length > 0)}
            onClick={approve}
          >
            {editing ? <Send className="size-4" /> : <CheckCircle2 className="size-4" />}
            {editing ? "Save & approve" : "Approve"}
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate({ action: "reject" })}
          >
            <XCircle className="size-4" />
            Reject
          </Button>
        </div>
      </div>

      {editing ? (
        <div className="mt-5 grid gap-4 md:grid-cols-3">
          <label className="space-y-2">
            <span className="text-xs font-medium text-muted-foreground">Audience</span>
            <Input
              className="bg-background/70"
              value={draft.audience}
              onChange={(event) =>
                setDraft((current) => ({ ...current, audience: event.target.value }))
              }
            />
          </label>
          <label className="space-y-2">
            <span className="text-xs font-medium text-muted-foreground">Tone</span>
            <Input
              className="bg-background/70"
              value={draft.tone}
              onChange={(event) =>
                setDraft((current) => ({ ...current, tone: event.target.value }))
              }
            />
          </label>
          <label className="space-y-2">
            <span className="text-xs font-medium text-muted-foreground">Kind</span>
            <select
              className="h-10 w-full border border-input bg-background/70 px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              value={draft.blog_kind}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  blog_kind: event.target.value as PlannedBlogKind,
                }))
              }
            >
              {blogKinds.map((kind) => (
                <option key={kind} value={kind}>
                  {kind.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}

      <div className="mt-5 grid gap-3">
        {draft.tasks.map((task, index) => (
          <div key={`${task.id}-${index}`} className="border bg-background/55 p-4">
            {editing ? (
              <div className="grid gap-3">
                <div className="grid gap-3 md:grid-cols-[1fr_8rem]">
                  <Input
                    value={task.title}
                    className="bg-background/70 font-medium"
                    onChange={(event) =>
                      updateTask(index, { title: event.target.value })
                    }
                  />
                  <Input
                    type="number"
                    min={120}
                    max={220}
                    value={task.target_words}
                    className="bg-background/70 font-mono"
                    onChange={(event) =>
                      updateTask(index, {
                        target_words: Number(event.target.value),
                      })
                    }
                  />
                </div>
                <Input
                  value={task.goal}
                  className="bg-background/70"
                  onChange={(event) => updateTask(index, { goal: event.target.value })}
                />
                <Textarea
                  value={task.bulletText}
                  className="min-h-28 bg-background/70"
                  onChange={(event) =>
                    updateTask(index, { bulletText: event.target.value })
                  }
                />
                <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
                  {(
                    [
                      ["requires_citations", "Citations"],
                      ["requires_code", "Code"],
                      ["requires_research", "Research"],
                    ] as const
                  ).map(([field, label]) => (
                    <label key={field} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={Boolean(task[field])}
                        onChange={(event) =>
                          updateTask(index, {
                            [field]: event.target.checked,
                          } as Partial<EditableTask>)
                        }
                      />
                      {label}
                    </label>
                  ))}
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-serif text-lg font-semibold">{task.title}</h3>
                  <span className="font-mono text-xs text-muted-foreground">
                    {task.target_words} words
                  </span>
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{task.goal}</p>
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6">
                  {task.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
                <div className="mt-3 flex flex-wrap gap-2">
                  {task.requires_citations ? (
                    <span className="border border-primary/20 bg-primary/10 px-2 py-1 text-xs text-primary">
                      citations
                    </span>
                  ) : null}
                  {task.requires_code ? (
                    <span className="border border-primary/20 bg-primary/10 px-2 py-1 text-xs text-primary">
                      code
                    </span>
                  ) : null}
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {editing && validation.length ? (
        <div className="mt-4 border border-destructive/35 bg-destructive/10 p-3 text-sm text-destructive">
          {validation[0]}
        </div>
      ) : null}
    </div>
  );
}
