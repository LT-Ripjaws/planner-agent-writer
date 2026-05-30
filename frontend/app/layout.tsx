import type { Metadata } from "next";

import { Providers } from "@/components/providers";
import { cn } from "@/lib/utils";

import "../styles/globals.css";

export const metadata: Metadata = {
  title: "Planner Agent Writer",
  description: "Local blog planning and writing workspace"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={cn("min-h-screen font-sans antialiased")}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
