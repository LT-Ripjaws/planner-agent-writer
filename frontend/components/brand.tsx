import Link from "next/link";

import { cn } from "@/lib/utils";

/** A small steaming coffee cup mark in caramel, with animated steam. */
export function BrewMark({ className }: { className?: string }) {
  return (
    <span
      className={cn("relative inline-block h-7 w-7", className)}
      aria-hidden="true"
    >
      <span className="pointer-events-none absolute inset-x-0 -top-1 mx-auto flex justify-center gap-[3px]">
        <span className="h-1.5 w-px animate-steam bg-primary/60" />
        <span className="h-1.5 w-px animate-steam bg-primary/45 [animation-delay:0.7s]" />
        <span className="h-1.5 w-px animate-steam bg-primary/50 [animation-delay:1.3s]" />
      </span>
      <svg viewBox="0 0 24 24" fill="none" className="h-full w-full">
        <path
          d="M4 9.5h11.5v4.5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4V9.5Z"
          fill="hsl(var(--primary))"
        />
        <path
          d="M15.5 10.5H18a2.5 2.5 0 0 1 0 5h-2.5"
          stroke="hsl(var(--primary))"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
        <path
          d="M3.5 18.75h12.5"
          stroke="hsl(var(--primary))"
          strokeWidth="1.7"
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

export function Brand({
  className,
  href = "/",
}: {
  className?: string;
  href?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "flex items-center gap-2.5 transition-opacity hover:opacity-90",
        className,
      )}
    >
      <BrewMark />
      <span className="font-serif text-xl font-semibold tracking-tight text-foreground">
        BrewNarrate
      </span>
    </Link>
  );
}
