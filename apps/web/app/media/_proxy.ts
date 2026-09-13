import { API_BASE, MEDIA_ID } from "@/lib/api";

/**
 * Same-origin passage for held media bytes.
 *
 * The browser asks this app for /media/<id>/...; the app asks the Library
 * service. Only an opaque media id is ever forwarded - a request carrying
 * anything else is answered here, without reaching the API - and only the
 * headers a player needs travel back.
 */
const PASSED_BACK = [
  "content-type",
  "content-length",
  "content-range",
  "accept-ranges",
  "cache-control",
  "x-content-type-options",
];

export async function proxyMedia(
  request: Request,
  id: string,
  suffix: string,
): Promise<Response> {
  if (!MEDIA_ID.test(id)) return new Response("Not found", { status: 404 });
  const headers: Record<string, string> = {};
  const range = request.headers.get("range");
  if (range) headers.range = range;
  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/library/media/${id}/${suffix}`, {
      headers,
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return new Response("The Library service is not reachable.", { status: 502 });
  }
  const out = new Headers();
  for (const name of PASSED_BACK) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}
