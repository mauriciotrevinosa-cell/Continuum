import "../_studio/studio.css";

/**
 * The viewer is immersive: no sidebar, no section bar - the work fills the
 * screen and one line leads back to it.
 */
export default function ViewLayout({ children }: { children: React.ReactNode }) {
  return <div className="studio viewer-shell">{children}</div>;
}
