import type { Metadata } from "next";
import type { ReactNode } from "react";

import { NavBar } from "@/components/NavBar";
import "./globals.css";

export const metadata: Metadata = {
  title: "TarifGuard Console",
  description:
    "Master-detail over the deterministic tarifhub serving API: tariff search, frozen-record detail, a human review form, and a labelled AI explain panel.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <NavBar />
        <main className="mx-auto max-w-5xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
