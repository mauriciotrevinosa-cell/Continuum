import "../_studio/studio.css";
import "../_studio/vault.css";
import "../_studio/catalog.css";

/** Watching is immersive, like the viewer: the episode fills the screen. */
export default function WatchLayout({ children }: { children: React.ReactNode }) {
  return <div className="studio viewer-shell">{children}</div>;
}
