import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { ExternalLink } from "lucide-react";

import { domainFromUrl } from "@/lib/format";
import { cn } from "@/lib/utils";

const components: Components = {
  h1: ({ className, ...props }) => (
    <h1
      className={cn("mb-6 text-4xl font-semibold leading-tight", className)}
      {...props}
    />
  ),
  h2: ({ className, ...props }) => (
    <h2
      className={cn(
        "mb-3 mt-9 border-b border-border pb-2 text-2xl font-semibold leading-tight",
        className,
      )}
      {...props}
    />
  ),
  h3: ({ className, ...props }) => (
    <h3 className={cn("mb-2 mt-6 text-xl font-semibold", className)} {...props} />
  ),
  p: ({ className, ...props }) => (
    <p className={cn("my-4 leading-8 text-foreground/90", className)} {...props} />
  ),
  ul: ({ className, ...props }) => (
    <ul className={cn("my-4 list-disc space-y-2 pl-6", className)} {...props} />
  ),
  ol: ({ className, ...props }) => (
    <ol className={cn("my-4 list-decimal space-y-2 pl-6", className)} {...props} />
  ),
  li: ({ className, ...props }) => (
    <li className={cn("leading-7 text-foreground/90", className)} {...props} />
  ),
  blockquote: ({ className, ...props }) => (
    <blockquote
      className={cn(
        "my-6 border-l-2 border-primary bg-primary/10 px-4 py-3 italic text-foreground/85",
        className,
      )}
      {...props}
    />
  ),
  a: ({ className, href = "", children, ...props }) => {
    const isExternal = /^https?:\/\//.test(href);
    return (
      <a
        className={cn(
          "inline-flex items-center gap-1 text-primary underline decoration-primary/35 underline-offset-4 hover:decoration-primary",
          className,
        )}
        href={href}
        target={isExternal ? "_blank" : undefined}
        // noopener/noreferrer prevents reverse-tabnabbing + referrer leak;
        // nofollow since these URLs come from untrusted web research.
        rel={isExternal ? "noopener noreferrer nofollow" : undefined}
        {...props}
      >
        <span>{children}</span>
        {isExternal ? (
          <span className="inline-flex items-center gap-1 border border-primary/25 bg-primary/10 px-1.5 py-0.5 font-mono text-[10px] no-underline">
            {domainFromUrl(href)}
            <ExternalLink className="size-3" />
          </span>
        ) : null}
      </a>
    );
  },
  pre: ({ className, ...props }) => (
    <pre
      className={cn(
        "my-6 overflow-x-auto border bg-background p-4 text-sm leading-6",
        className,
      )}
      {...props}
    />
  ),
  code: ({ className, ...props }) => (
    <code
      className={cn(
        "font-mono text-sm",
        !className && "bg-muted px-1.5 py-0.5 text-primary",
        className,
      )}
      {...props}
    />
  ),
  table: ({ className, ...props }) => (
    <div className="my-6 overflow-x-auto border">
      <table className={cn("w-full min-w-[36rem] text-sm", className)} {...props} />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th
      className={cn("border-b bg-muted px-3 py-2 text-left font-semibold", className)}
      {...props}
    />
  ),
  td: ({ className, ...props }) => (
    <td className={cn("border-b px-3 py-2 align-top", className)} {...props} />
  ),
};

export function MarkdownViewer({
  markdown,
  className,
}: {
  markdown: string;
  className?: string;
}) {
  return (
    <article
      className={cn(
        "bn-markdown max-w-none font-serif text-[1.05rem] text-foreground",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={components}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
