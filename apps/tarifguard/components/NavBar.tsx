"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * Top navigation, shared by every screen. Carries the single brand logo (the tarifhub
 * wordmark appears exactly once per surface, here) plus the TarifGuard sub-brand
 * wayfinding accent (the Guard shield). The four console surfaces are linked here.
 */
const LINKS = [
  { href: "/search", label: "Search" },
  { href: "/review", label: "Review" },
  { href: "/explain", label: "Explain" },
  { href: "/coding-check", label: "Coding check" },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <header className="border-b border-line bg-card">
      <nav className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="flex items-center gap-3" aria-label="TarifGuard Console — home">
          {/* eslint-disable-next-line @next/next/no-img-element -- brand SVG, rendered verbatim */}
          <img src="/logo-primary.svg" alt="tarifhub" className="h-7 w-auto" />
          <span className="hidden items-center gap-1.5 border-l border-line pl-3 sm:flex">
            {/* eslint-disable-next-line @next/next/no-img-element -- Guard wayfinding mark */}
            <img src="/tarifguard-mark.svg" alt="" className="h-5 w-5" />
            <span className="text-sm font-semibold text-navy">TarifGuard Console</span>
          </span>
        </Link>
        <ul className="flex items-center gap-1 text-sm">
          {LINKS.map((link) => {
            const active = pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <li key={link.href}>
                <Link
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded px-3 py-1.5 transition ${
                    active
                      ? "bg-navy/5 font-medium text-navy"
                      : "text-body hover:bg-bg hover:text-navy"
                  }`}
                >
                  {link.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
