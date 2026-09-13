"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A navigation link that knows whether it is where you are.
 *
 * `exact` is for a section index that is the parent of other screens; `also`
 * lists screens that belong to this entry without living under its path
 * (Acquisition owns Sources and the Calendar as well as the Queue).
 */
export function SideLink({
  href,
  exact = false,
  also = [],
  className = "side-link",
  children,
}: {
  href: string;
  exact?: boolean;
  also?: string[];
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const under = (base: string) => pathname === base || pathname.startsWith(`${base}/`);
  const active = exact ? pathname === href : under(href) || also.some(under);
  return (
    <Link href={href} className={className} data-active={active} aria-current={active ? "page" : undefined}>
      {children}
    </Link>
  );
}
