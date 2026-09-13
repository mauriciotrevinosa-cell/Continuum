import { StudioShell } from "../_studio/StudioShell";

export default function ProductionLayout({ children }: { children: React.ReactNode }) {
  return <StudioShell>{children}</StudioShell>;
}
