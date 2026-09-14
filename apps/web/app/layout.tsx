import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Continuum Studio",
  description: "Local-first studio over your read-only Source Vault: library, references and production.",
};

/**
 * The root frame. Screens appear in the phase that builds them (F-67): no
 * placeholder navigation to features that do not exist yet.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
