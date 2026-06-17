"use client";

import { AlertTriangle, CheckCircle2, Clock, PauseCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useRuns } from "@/lib/use-runs";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

type Stat = {
  label: string;
  icon: LucideIcon;
  accent: string;
  count: (statuses: string[]) => number;
};

const stats: Stat[] = [
  {
    label: "Brewed",
    icon: CheckCircle2,
    accent: "text-success",
    count: (statuses) =>
      statuses.filter((s) => s === "completed" || s === "completed_with_warnings")
        .length,
  },
  {
    label: "Live",
    icon: Clock,
    accent: "text-primary",
    count: (statuses) =>
      statuses.filter((s) => ["queued", "running"].includes(s)).length,
  },
  {
    label: "Review",
    icon: PauseCircle,
    accent: "text-warning",
    count: (statuses) => statuses.filter((s) => s === "awaiting_approval").length,
  },
  {
    label: "Failed",
    icon: AlertTriangle,
    accent: "text-destructive",
    count: (statuses) => statuses.filter((s) => s === "failed").length,
  },
];

export function QuickStats() {
  const { data: runs, isLoading } = useRuns(20);

  if (isLoading) {
    return <Skeleton className="h-20 w-full" />;
  }

  const statuses = runs?.map((run) => run.status) ?? [];

  return (
    <div className="flex items-stretch divide-x divide-border/60 border bg-card/40">
      {stats.map((stat) => {
        const Icon = stat.icon;
        const value = stat.count(statuses);
        const dim = value === 0;
        return (
          <div key={stat.label} className="flex-1 px-3 py-4 text-center">
            <Icon
              className={cn(
                "mx-auto size-4",
                dim ? "text-muted-foreground/40" : stat.accent,
              )}
            />
            <p
              className={cn(
                "mt-2 font-mono text-2xl leading-none",
                dim ? "text-muted-foreground/50" : stat.accent,
              )}
            >
              {value}
            </p>
            <p className="mt-1.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {stat.label}
            </p>
          </div>
        );
      })}
    </div>
  );
}
