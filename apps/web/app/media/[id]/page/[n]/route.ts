import { proxyMedia } from "../../../_proxy";

export const dynamic = "force-dynamic";

/** One page of an image archive, addressed by position. */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string; n: string }> },
) {
  const { id, n } = await params;
  if (!/^\d{1,6}$/.test(n)) return new Response("Not found", { status: 404 });
  return proxyMedia(request, id, `pages/${Number(n)}`);
}
