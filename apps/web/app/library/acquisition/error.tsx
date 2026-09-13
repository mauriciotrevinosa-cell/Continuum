"use client";

/**
 * Something failed while rendering a Library screen.
 *
 * The person sees what they can do; the error text is available, folded.
 */
export default function LibraryError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="empty" role="alert">
      <h3>This screen could not be shown</h3>
      <p>The Library data may be mid-update. Try again in a moment.</p>
      <div className="actions">
        <button className="button primary" type="button" onClick={reset}>
          Try again
        </button>
      </div>
      <details className="disclosure" style={{ marginTop: 18 }}>
        <summary>Technical details</summary>
        <div className="disclosure-body">
          <code>{error.message}</code>
        </div>
      </details>
    </div>
  );
}
