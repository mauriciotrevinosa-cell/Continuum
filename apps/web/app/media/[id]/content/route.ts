import { proxyMedia } from "../../_proxy";

export const dynamic = "force-dynamic";

/** A video or document, streamed with byte ranges so players can seek. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyMedia(request, id, "content");
}
