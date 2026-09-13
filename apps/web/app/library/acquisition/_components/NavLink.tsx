"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A navigation link that knows whether it is the screen you are on.
 *
 * `exact` matters for a section index: /library/acquisition is the parent of
 * every other screen here, so without it the Overview tab would look active
 * on all of them.
 */
export function NavLink({
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
