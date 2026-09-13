"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function SubnavLink({
  href,
  exact = false,
  children,
}: {
  href: string;
  exact?: boolean;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link href={href} data-active={active} aria-current={active ? "page" : undefined}>
      {children}
    </Link>
  );
}
