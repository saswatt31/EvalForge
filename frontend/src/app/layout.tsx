import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "EvalForge | RAG evaluation and latency benchmarks",
    template: "%s | EvalForge",
  },
  description:
    "Run golden datasets against any RAG pipeline, measure quality with inspectable evidence, and benchmark latency.",
  icons: {
    icon: "/evalforge-mark.svg",
  },
};

export const viewport: Viewport = {
  themeColor: "#080b0e",
  colorScheme: "dark",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
