export interface LinkEntry {
  url: string;
  creator_handle: string | null;
  tags: string[];
}

/**
 * Pasted text -> link entries for the Reference Inbox.
 *
 * Every http(s) token starts a new entry; @handle and #tag tokens belong to the
 * link before them. Several links on one line - or a paste whose line breaks
 * were lost - still come apart correctly. Nothing here opens a link.
 */
export function parseLinks(text: string): LinkEntry[] {
  const entries: LinkEntry[] = [];
  for (const token of text.split(/\s+/).filter(Boolean)) {
    const at = token.search(/https?:\/\//i);
    const last = entries[entries.length - 1];
    if (at >= 0) {
      const prefix = token.slice(0, at);
      if (last && prefix.startsWith("#") && prefix.length > 1) last.tags.push(prefix.slice(1));
      entries.push({ url: token.slice(at), creator_handle: null, tags: [] });
    } else if (last && token.startsWith("@") && token.length > 1 && !last.creator_handle) {
      last.creator_handle = token;
    } else if (last && token.startsWith("#") && token.length > 1) {
      last.tags.push(token.slice(1));
    }
  }
  return entries;
}
