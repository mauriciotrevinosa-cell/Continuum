import { proxyMember } from "../../../_proxy";

export const dynamic = "force-dynamic";

/** A prepared video from inside an archive, streamed with byte ranges. */
export async function GET(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyMember(request, id);
}
