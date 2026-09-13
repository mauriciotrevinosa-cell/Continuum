import { StudioShell } from "../_studio/StudioShell";

export default function LibraryLayout({ children }: { children: React.ReactNode }) {
  return <StudioShell>{children}</StudioShell>;
}
