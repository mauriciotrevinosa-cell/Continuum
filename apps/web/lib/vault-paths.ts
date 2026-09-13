/**
 * Which API paths the browser may reach through this app's /vault-api passage.
 *
 * Every segment is an id, a project key or a fixed word. There is no segment
 * that can carry a filesystem path, a filename or a traversal: anything that
 * does not match one of these shapes is answered 404 without reaching the API.
 */

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const PROJECT = "[a-z0-9][a-z0-9-]{0,79}";

const ALLOWED: RegExp[] = [
  new RegExp(`^library/characters(/${UUID}(/(update|remove|outfits))?)?$`),
  new RegExp(`^library/outfits/${UUID}/(update|remove)$`),
  new RegExp(`^library/visual-modes(/${UUID}/(update|remove))?$`),
  new RegExp(
    `^library/references(/from-source|/${UUID}(/(image|update|remove|uses|characters|techniques|descriptors|standings|panel-sources))?)?$`,
  ),
  new RegExp(`^library/reference-(characters|techniques|descriptors|standings)/${UUID}/(preferred|remove)$`),
  new RegExp(`^library/panel-sources/${UUID}/remove$`),
  new RegExp(
    `^library/inbox(/(urls|batches|files|frames|bulk-update|bulk-accept)|/candidates/${UUID}(/(content|clip-frame|attach|update|dismiss|restore|accept))?)?$`,
  ),
  new RegExp(`^projects/${PROJECT}/(visual-modes(/${UUID}/remove)?|panel-sources|rough-artifacts)$`),
  new RegExp(
    `^production/(readiness|rough-artifacts/${UUID}(/attempts)?|attempts/${UUID}(/(provenance|image|review|continuity))?)$`,
  ),
  new RegExp(`^jobs/${UUID}/retry$`),
];

/** The API path for these route segments, or null when it is not allowed. */
export function allowedVaultPath(segments: string[]): string | null {
  if (!segments.length || segments.some((s) => !s || s === "." || s === ".." || /[\\/%:]/.test(s))) {
    return null;
  }
  const path = segments.join("/");
  return ALLOWED.some((pattern) => pattern.test(path)) ? path : null;
}
