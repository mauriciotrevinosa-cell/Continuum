"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname();
  const active = href === "/library/acquisition" ? pathname === href : pathname.startsWith(href);
  return (
    <Link href={href} data-active={active}>
      {children}
    </Link>
  );
}
