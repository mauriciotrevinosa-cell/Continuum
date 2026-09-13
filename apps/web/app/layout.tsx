import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Continuum — Phase 0",
  description: "Local-first Source Vault and multiverse story studio (foundation).",
};

/**
 * Deliberately no navigation to Library, Reader, Story Studio, Character
 * Brain or Visual Lab (F-67). A placeholder screen for an unbuilt feature
 * creates the impression of progress that does not exist and invites
 * premature backend stubs. Screens appear in the phase that builds them.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
