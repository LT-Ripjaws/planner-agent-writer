"use client";

import * as React from "react";
import Link from "next/link";

import { Brand } from "@/components/brand";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SiteHeader() {
  const [scrolled, setScrolled] = React.useState(false);

  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 transition-colors duration-300",
        scrolled
          ? "border-b border-border/60 bg-background/80 backdrop-blur-md"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <div className="flex h-16 w-full items-center justify-between px-6 sm:px-8 lg:px-10">
        <Brand />
        <nav
          className={cn(
            "hidden items-center gap-8 text-sm md:flex",
            scrolled ? "text-muted-foreground" : "text-foreground/80",
          )}
        >
          <Link href="#how" className="transition-colors hover:text-primary">
            How it works
          </Link>
          <Link href="#showcase" className="transition-colors hover:text-primary">
            The workspace
          </Link>
        </nav>
        <Button asChild>
          <Link href="/dashboard">Start brewing</Link>
        </Button>
      </div>
    </header>
  );
}
