import { API_BASE } from "@/lib/api";
import { allowedVaultPath } from "@/lib/vault-paths";

export const dynamic = "force-dynamic";

/**
 * Same-origin passage from the browser to the reference vault and rough
 * production routes of the API.
 *
 * Only allowlisted id-shaped paths are forwarded (see lib/vault-paths.ts); the
 * body and query travel as they are, and the API validates both. Only the
 * headers a page needs come back.
 */
const PASSED_BACK = ["content-type", "content-length", "cache-control", "x-content-type-options"];

async function forward(request: Request, segments: string[]): Promise<Response> {
  const path = allowedVaultPath(segments);
  if (!path) return new Response("Not found", { status: 404 });
  const url = new URL(request.url);
  const headers: Record<string, string> = {};
  const type = request.headers.get("content-type");
  if (type) headers["content-type"] = type;
  let upstream: Response;
  try {
    upstream = await fetch(`${API_BASE}/${path}${url.search}`, {
      method: request.method,
      headers,
      body: request.method === "POST" ? await request.arrayBuffer() : undefined,
      cache: "no-store",
      signal: request.signal,
    });
  } catch {
    return Response.json(
      { detail: { message: "The Continuum API is not reachable. Start it, then try again." } },
      { status: 502 },
    );
  }
  const out = new Headers();
  for (const name of PASSED_BACK) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return forward(request, (await params).path);
}

export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return forward(request, (await params).path);
}
