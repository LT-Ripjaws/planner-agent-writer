"use client";

import { useRouter } from "next/navigation";
import { BookOpen, ChevronDown, Loader2, Search, Sparkles } from "lucide-react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { ApiError, createRun } from "@/lib/api";
import type { BlogKind, BlogRunCreate, ResearchMode, Tone } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

const toneOptions: { value: Tone; label: string }[] = [
  { value: "neutral", label: "Neutral" },
  { value: "technical", label: "Technical" },
  { value: "casual", label: "Casual" },
  { value: "authoritative", label: "Authoritative" },
];

const kindOptions: { value: BlogKind; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "explainer", label: "Explainer" },
  { value: "tutorial", label: "Tutorial" },
  { value: "news_roundup", label: "News roundup" },
  { value: "comparison", label: "Comparison" },
  { value: "system_design", label: "System design" },
];

const researchOptions: {
  value: ResearchMode;
  label: string;
  icon: typeof Sparkles;
}[] = [
  { value: "auto", label: "Auto", icon: Sparkles },
  { value: "required", label: "Research", icon: Search },
  { value: "off", label: "Closed", icon: BookOpen },
];

function errorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 429) return "Too many runs. Let the kettle cool a moment.";
    if (error.status === 422) return error.message || "Check the topic details.";
    return error.message;
  }

  return "The backend did not answer. Is uvicorn running on port 8000?";
}

export function TopicForm({ className }: { className?: string }) {
  const router = useRouter();
  const {
    control,
    formState: { errors, isSubmitting },
    handleSubmit,
    register,
    setValue,
  } = useForm<BlogRunCreate>({
    mode: "onChange",
    defaultValues: {
      topic: "",
      audience: "",
      tone: "neutral",
      blog_kind: "auto",
      research_mode: "auto",
    },
  });

  const topic = useWatch({ control, name: "topic" }) || "";
  const researchMode = useWatch({ control, name: "research_mode" }) || "auto";

  async function onSubmit(values: BlogRunCreate) {
    try {
      const payload: BlogRunCreate = {
        ...values,
        topic: values.topic.trim(),
        audience: values.audience?.trim() || null,
      };
      const run = await createRun(payload);
      toast.success("Run queued");
      router.push(`/runs/${run.id}`);
    } catch (error) {
      toast.error(errorMessage(error));
    }
  }

  return (
    <form
      className={cn("space-y-5", className)}
      onSubmit={handleSubmit(onSubmit)}
    >
      <div className="space-y-2">
        <div className="flex items-end justify-between gap-3">
          <label className="text-sm font-medium text-foreground" htmlFor="topic">
            Topic
          </label>
          <span
            className={cn(
              "font-mono text-xs",
              topic.length > 460 ? "text-warning" : "text-muted-foreground",
            )}
          >
            {topic.length}/500
          </span>
        </div>
        <Textarea
          id="topic"
          placeholder="What should BrewNarrate write about?"
          className="min-h-32 resize-none bg-background/70 text-base leading-7"
          maxLength={500}
          {...register("topic", {
            required: "Give the agent a topic to brew.",
            minLength: { value: 3, message: "Topic needs at least 3 characters." },
            maxLength: { value: 500, message: "Topic must stay under 500 characters." },
            validate: (value) =>
              value.trim().length >= 3 || "Topic needs at least 3 characters.",
          })}
        />
        {errors.topic ? (
          <p className="text-sm text-destructive">{errors.topic.message}</p>
        ) : null}
      </div>

      <div className="space-y-2">
        <span className="text-sm font-medium text-foreground">Research mode</span>
        <div
          className="grid grid-cols-3 gap-1 border bg-muted/45 p-1"
          role="radiogroup"
          aria-label="Research mode"
        >
          {researchOptions.map((option) => {
            const Icon = option.icon;
            const active = researchMode === option.value;
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={active}
                className={cn(
                  "flex h-10 items-center justify-center gap-2 px-2 text-sm font-medium text-muted-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active && "bg-primary text-primary-foreground",
                )}
                onClick={() =>
                  setValue("research_mode", option.value, { shouldDirty: true })
                }
              >
                <Icon className="size-4" />
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Controller
          control={control}
          name="tone"
          render={({ field }) => (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Tone</label>
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="bg-background/70">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {toneOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        />

        <Controller
          control={control}
          name="blog_kind"
          render={({ field }) => (
            <div className="space-y-2">
              <label className="text-sm font-medium text-foreground">Kind</label>
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger className="bg-background/70">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {kindOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        />
      </div>

      <details className="group border bg-card/60 p-4">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground">
          Audience notes
          <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-3 space-y-2">
          <label className="sr-only" htmlFor="audience">
            Audience
          </label>
          <Input
            id="audience"
            placeholder="Example: senior Python engineers, early-stage founders"
            className="bg-background/70"
            {...register("audience")}
          />
        </div>
      </details>

      <Button className="h-11 w-full" type="submit" disabled={isSubmitting}>
        {isSubmitting ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Sparkles className="size-4" />
        )}
        Start brewing
      </Button>
    </form>
  );
}
