"use client";

import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  CheckCircle2,
  Clipboard,
  Download,
  FileText,
  Link as LinkIcon,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";

import { getResult, getRun } from "@/lib/api";
import { domainFromUrl, humanizeToken, wordCount } from "@/lib/format";
import type { BlogRunDetail, BlogRunResult, Plan, QualityReport } from "@/lib/types";
import { useRunEvents } from "@/lib/use-run-events";
import { cn } from "@/lib/utils";
import { DeleteRunButton } from "@/components/delete-run-button";
import { MarkdownViewer } from "@/components/markdown-viewer";
import { PlanReview } from "@/components/plan-review";
import { ResumeButton } from "@/components/resume-button";
import { RunProgress } from "@/components/run-progress";
import { StatusBadge } from "@/components/status-badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const resultStatuses = new Set(["completed", "completed_with_warnings"]);
const liveStatuses = new Set(["queued", "running", "awaiting_approval"]);

function QualitySummary({ report }: { report?: QualityReport | null }) {
  if (!report) {
    return (
      <div className="border bg-card/60 p-5 text-sm text-muted-foreground">
        No quality report was stored for this run.
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="border bg-card/60 p-5">
        <span className="text-sm text-muted-foreground">Overall score</span>
        <p className="mt-2 font-mono text-4xl text-primary">
          {report.overall_score.toFixed(1)}
        </p>
      </div>
      <div className="border bg-card/60 p-5">
        <span className="text-sm text-muted-foreground">Completeness</span>
        <p className="mt-2 font-mono text-4xl text-primary">
          {Math.round(report.completeness * 100)}%
        </p>
      </div>
      <div className="border bg-card/60 p-5">
        <span className="text-sm text-muted-foreground">Tone match</span>
        <p className="mt-2 text-lg font-medium">
          {report.tone_match ? "Matched" : "Needs attention"}
        </p>
      </div>
      <div className="border bg-card/60 p-5">
        <span className="text-sm text-muted-foreground">On topic</span>
        <p className="mt-2 text-lg font-medium">
          {report.on_topic ? "Yes" : "No"}
        </p>
      </div>
      <div className="border bg-card/60 p-5 md:col-span-2">
        <h3 className="font-semibold">Issues</h3>
        {report.issues.length ? (
          <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
            {report.issues.map((issue, index) => (
              <li key={`${issue.task_id}-${issue.category}-${index}`}>
                Task {issue.task_id}: {issue.description}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-muted-foreground">No issues reported.</p>
        )}
      </div>
    </div>
  );
}

function SourcesTab({ result }: { result: BlogRunResult }) {
  if (!result.evidence.length) {
    return (
      <div className="border bg-card/60 p-5 text-sm text-muted-foreground">
        This run did not persist source evidence.
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {result.evidence.map((item, index) => (
        <a
          key={`${item.url}-${index}`}
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="block border bg-card/60 p-4 transition-colors hover:bg-accent/45"
        >
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <LinkIcon className="size-3.5 text-primary" />
            <span className="font-mono">{domainFromUrl(item.url)}</span>
            {item.score !== null && item.score !== undefined ? (
              <span className="font-mono">score {item.score.toFixed(2)}</span>
            ) : null}
          </div>
          <h3 className="mt-2 font-medium text-foreground">{item.title}</h3>
          <p className="mt-2 line-clamp-3 text-sm leading-6 text-muted-foreground">
            {item.snippet}
          </p>
        </a>
      ))}
    </div>
  );
}

function PlanTab({ plan }: { plan?: Plan | null }) {
  if (!plan) {
    return (
      <div className="border bg-card/60 p-5 text-sm text-muted-foreground">
        No plan was stored for this run.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="border bg-card/60 p-5">
        <h3 className="text-xl font-semibold">{plan.blog_title}</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {plan.audience} / {plan.tone} / {humanizeToken(plan.blog_kind)}
        </p>
      </div>
      {plan.tasks.map((task) => (
        <div key={task.id} className="border bg-card/60 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-semibold">{task.title}</h4>
            <span className="font-mono text-xs text-muted-foreground">
              {task.target_words} words
            </span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{task.goal}</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-foreground/85">
            {task.bullets.map((bullet) => (
              <li key={bullet}>{bullet}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function WarningsTab({ warnings }: { warnings: string[] }) {
  if (!warnings.length) {
    return (
      <div className="border bg-card/60 p-5 text-sm text-muted-foreground">
        No warnings for this run.
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {warnings.map((warning, index) => (
        <li
          key={`${warning}-${index}`}
          className="border border-warning/30 bg-warning/10 p-4 text-sm text-warning"
        >
          {warning}
        </li>
      ))}
    </ul>
  );
}

function ArticleSkeleton() {
  return (
    <div className="border bg-card/60 p-6">
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="mt-6 h-4 w-full" />
      <Skeleton className="mt-3 h-4 w-11/12" />
      <Skeleton className="mt-3 h-4 w-10/12" />
      <Skeleton className="mt-8 h-6 w-1/2" />
      <Skeleton className="mt-4 h-4 w-full" />
      <Skeleton className="mt-3 h-4 w-9/12" />
    </div>
  );
}

function ResultTabs({
  result,
  warnings,
}: {
  result: BlogRunResult;
  warnings: string[];
}) {
  return (
    <Tabs defaultValue="article">
      <TabsList className="grid h-auto w-full grid-cols-2 md:grid-cols-5">
        <TabsTrigger value="article">Article</TabsTrigger>
        <TabsTrigger value="sources">Sources</TabsTrigger>
        <TabsTrigger value="quality">Quality</TabsTrigger>
        <TabsTrigger value="plan">Plan</TabsTrigger>
        <TabsTrigger value="warnings">Warnings</TabsTrigger>
      </TabsList>
      <TabsContent value="article">
        <div className="border bg-card/60 p-5 md:p-7">
          <MarkdownViewer markdown={result.markdown} />
        </div>
      </TabsContent>
      <TabsContent value="sources">
        <SourcesTab result={result} />
      </TabsContent>
      <TabsContent value="quality">
        <QualitySummary report={result.quality_report} />
      </TabsContent>
      <TabsContent value="plan">
        <PlanTab plan={result.plan} />
      </TabsContent>
      <TabsContent value="warnings">
        <WarningsTab warnings={warnings} />
      </TabsContent>
    </Tabs>
  );
}

function saveMarkdown(filename: string, markdown: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  // Defer revoke so the download isn't cancelled mid-flight in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function RunDetailClient({
  runId,
  initialRun,
}: {
  runId: string;
  initialRun: BlogRunDetail;
}) {
  const queryClient = useQueryClient();
  const [streamKey, setStreamKey] = useState(0);
  const stream = useRunEvents(runId, true, streamKey);
  const detailQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
    initialData: initialRun,
    refetchInterval: (query) =>
      liveStatuses.has(query.state.data?.status ?? "") ? 2500 : false,
  });

  const run = detailQuery.data;
  const status = stream.status ?? run.status;
  const warnings = useMemo(
    () => Array.from(new Set([...(run.warnings ?? []), ...stream.warnings])),
    [run.warnings, stream.warnings],
  );

  const resultQuery = useQuery({
    queryKey: ["run-result", runId],
    queryFn: () => getResult(runId),
    enabled: resultStatuses.has(status),
    retry: false,
  });

  useEffect(() => {
    if (!stream.finished) return;
    void queryClient.invalidateQueries({ queryKey: ["run", runId] });
    if (resultStatuses.has(stream.status ?? "")) {
      void queryClient.invalidateQueries({ queryKey: ["run-result", runId] });
    }
  }, [queryClient, runId, stream.finished, stream.status]);

  const result = resultQuery.data;
  const title =
    result?.plan?.blog_title || stream.blogTitle || run.blog_title || run.topic;
  const awaitingPlan =
    status === "awaiting_approval" ? stream.awaitingPlan ?? run.plan : null;
  const markdown = result?.markdown ?? run.markdown ?? "";
  const qualityScore = result?.quality_report?.overall_score ?? stream.qualityScore;

  async function copyMarkdown() {
    if (!markdown) return;
    await navigator.clipboard.writeText(markdown);
    toast.success("Markdown copied");
  }

  return (
    <div className="mx-auto grid max-w-7xl gap-6 px-5 py-8 lg:grid-cols-[23rem_minmax(0,1fr)] lg:px-8">
      <aside className="space-y-4">
        <RunProgress
          state={stream}
          initialStatus={run.status}
          initialStep={run.progress_step}
          initialMode={run.mode}
        />
      </aside>

      <section className="min-w-0 space-y-5">
        <div className="border bg-card/70 p-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={status} />
                {run.mode || stream.mode ? (
                  <span className="border bg-background/60 px-2 py-1 font-mono text-xs text-muted-foreground">
                    {humanizeToken(stream.mode || run.mode)}
                  </span>
                ) : null}
                {qualityScore !== null && qualityScore !== undefined ? (
                  <span className="inline-flex items-center gap-1 border border-primary/25 bg-primary/10 px-2 py-1 font-mono text-xs text-primary">
                    <Sparkles className="size-3" />
                    {qualityScore.toFixed(1)}
                  </span>
                ) : null}
                {markdown ? (
                  <span className="border bg-background/60 px-2 py-1 font-mono text-xs text-muted-foreground">
                    {wordCount(markdown)} words
                  </span>
                ) : null}
              </div>
              <h1 className="mt-4 text-3xl font-semibold leading-tight md:text-4xl">
                {title}
              </h1>
            </div>

            {markdown || resultStatuses.has(status) ? (
              <div className="flex flex-wrap gap-2">
                {markdown ? (
                  <>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={copyMarkdown}
                    >
                      <Clipboard className="size-4" />
                      Copy MD
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => saveMarkdown(`${run.id}.md`, markdown)}
                    >
                      <Download className="size-4" />
                      Download
                    </Button>
                  </>
                ) : null}
                {resultStatuses.has(status) ? (
                  <DeleteRunButton
                    runId={runId}
                    title={title}
                    showLabel
                    redirectToDashboard
                  />
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        {awaitingPlan ? (
          <PlanReview
            key={`${awaitingPlan.blog_title}-${awaitingPlan.tasks.length}`}
            runId={runId}
            plan={awaitingPlan}
            onResolved={() => setStreamKey((value) => value + 1)}
          />
        ) : null}

        {status === "failed" ? (
          <div className="space-y-4">
            <div className="border border-destructive/35 bg-destructive/10 p-5 text-destructive">
              <div className="flex items-center gap-2 font-medium">
                <AlertCircle className="size-4" />
                Run failed
              </div>
              <p className="mt-2 text-sm text-destructive/85">
                {stream.error || run.error || "The run stopped before completion."}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <ResumeButton
                  runId={runId}
                  onResumed={() => setStreamKey((value) => value + 1)}
                />
                <DeleteRunButton
                  runId={runId}
                  title={title}
                  showLabel
                  redirectToDashboard
                />
              </div>
            </div>
            <WarningsTab warnings={warnings} />
            {run.markdown ? (
              <div className="border bg-card/60 p-5">
                <div className="mb-4 flex items-center gap-2 text-sm font-medium">
                  <FileText className="size-4 text-primary" />
                  Partial draft
                </div>
                <MarkdownViewer markdown={run.markdown} />
              </div>
            ) : null}
          </div>
        ) : resultStatuses.has(status) ? (
          resultQuery.isLoading || !result ? (
            <ArticleSkeleton />
          ) : (
            <ResultTabs result={result} warnings={warnings} />
          )
        ) : (
          <div
            className={cn(
              "space-y-4",
              status === "awaiting_approval" && awaitingPlan ? "hidden" : "",
            )}
          >
            <ArticleSkeleton />
            <div className="border bg-card/60 p-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="size-4 text-primary" />
                Draft output will appear here when the run completes.
              </div>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
