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
  return proxyStream(request, `/library/media/${id}/${suffix}`);
}

const MEMBER_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** A video inside an archive, once the worker has prepared it - by member id only. */
export async function proxyMember(request: Request, id: string): Promise<Response> {
  if (!MEMBER_ID.test(id)) return new Response("Not found", { status: 404 });
  return proxyStream(request, `/catalog/members/${id}/content`);
}

async function proxyStream(request: Request, upstreamPath: string): Promise<Response> {
  const headers: Record<string, string> = {};
  const range = request.headers.get("range");
  if (range) headers.range = range;
  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}${upstreamPath}`, {
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
