import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Coffee,
  Loader2,
  PauseCircle,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type StatusMeta = {
  label: string;
  icon: LucideIcon;
  className: string;
  spin?: boolean;
};

const STATUS_META: Record<string, StatusMeta> = {
  queued: {
    label: "Queued",
    icon: Clock,
    className: "bg-muted text-muted-foreground",
  },
  running: {
    label: "Brewing",
    icon: Loader2,
    className: "bg-primary/15 text-primary",
    spin: true,
  },
  awaiting_approval: {
    label: "Needs review",
    icon: PauseCircle,
    className: "bg-warning/15 text-warning",
  },
  completed: {
    label: "Brewed",
    icon: CheckCircle2,
    className: "bg-success/15 text-success",
  },
  completed_with_warnings: {
    label: "Brewed · notes",
    icon: AlertTriangle,
    className: "bg-warning/15 text-warning",
  },
  failed: {
    label: "Failed",
    icon: XCircle,
    className: "bg-destructive/15 text-destructive",
  },
};

const FALLBACK: StatusMeta = {
  label: "Unknown",
  icon: Coffee,
  className: "bg-muted text-muted-foreground",
};

export function statusMeta(status: string): StatusMeta {
  return STATUS_META[status] ?? { ...FALLBACK, label: status };
}

export function StatusBadge({
  status,
  className,
  size = "md",
}: {
  status: string;
  className?: string;
  size?: "sm" | "md";
}) {
  const meta = statusMeta(status);
  const Icon = meta.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs",
        meta.className,
        className,
      )}
    >
      <Icon
        className={cn(
          size === "sm" ? "size-3" : "size-3.5",
          meta.spin && "animate-spin",
        )}
      />
      {meta.label}
    </span>
  );
}
