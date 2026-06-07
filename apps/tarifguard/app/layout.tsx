import type { Metadata } from "next";
import type { ReactNode } from "react";

import { NavBar } from "@/components/NavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "TarifGuard",
  description:
    "Practice-facing front end over the deterministic TarifHub serving API: tariff search, coding checks, and de-identified explanations.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <NavBar />
        <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
