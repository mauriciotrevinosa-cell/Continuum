/** Shown while a Library screen reads its documents: the shape, not a spinner. */
export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading the Library">
      <div className="skeleton" style={{ height: 14, width: 120, marginBottom: 14 }} />
      <div className="skeleton" style={{ height: 44, width: 360, marginBottom: 36 }} />
      <div className="skeleton" style={{ height: 220, marginBottom: 22 }} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
        <div className="skeleton" style={{ height: 180 }} />
        <div className="skeleton" style={{ height: 180 }} />
        <div className="skeleton" style={{ height: 180 }} />
      </div>
    </div>
  );
}
