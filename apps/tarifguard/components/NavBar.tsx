import Link from "next/link";

const LINKS = [
  { href: "/search", label: "Search" },
  { href: "/coding-check", label: "Coding check" },
  { href: "/explain", label: "Explain" },
];

/** Top navigation shared by every screen. */
export function NavBar() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
        <Link href="/" className="font-semibold text-brand-dark">
          TarifGuard
        </Link>
        <ul className="flex gap-4 text-sm">
          {LINKS.map((link) => (
            <li key={link.href}>
              <Link href={link.href} className="text-slate-600 hover:text-brand">
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
