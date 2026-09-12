"use server";

/**
 * Actions the acquisition screens can take.
 *
 * Every one of them calls the API, which runs an allowlisted verb of the
 * acquisition CLI. Nothing here can write into the Source Vault: applying a
 * scaffold or an import is deliberately absent, and the screens show the
 * command to run instead. The result always carries that command, so the
 * user can see - and repeat - exactly what happened.
 */

import { revalidatePath } from "next/cache";
import { ACCESS_MODELS, type AccessModel, ApiUnreachableError, acquisition } from "@/lib/api";

export interface ActionState {
  ok: boolean;
  message: string;
  command?: string;
  output?: string;
}

const SCREENS = [
  "/library/acquisition",
  "/library/acquisition/sources",
  "/library/acquisition/queue",
  "/library/acquisition/calendar",
  "/library/acquisition/intake",
  "/library/acquisition/updates",
];

async function run(
  work: () => Promise<{ ok: boolean; message: string; command: string; output: string }>,
): Promise<ActionState> {
  try {
    const result = await work();
    for (const screen of SCREENS) revalidatePath(screen);
    return {
      ok: result.ok,
      message: result.message,
      command: result.command,
      output: result.output,
    };
  } catch (cause) {
    return {
      ok: false,
      message:
        cause instanceof ApiUnreachableError
          ? cause.message
          : `The action failed: ${String(cause)}`,
    };
  }
}

function text(form: FormData, key: string): string | null {
  const value = form.get(key);
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length ? trimmed : null;
}

/** Only a value the API declares is forwarded; anything else is dropped. */
function accessModel(value: string | null): AccessModel | null {
  return ACCESS_MODELS.includes(value as AccessModel) ? (value as AccessModel) : null;
}


export async function addSourceAction(
  _previous: ActionState | null,
  form: FormData,
): Promise<ActionState> {
  const url = text(form, "url");
  if (!url) {
    return { ok: false, message: "Give a website URL or the path of a folder you own." };
  }
  const adapter = text(form, "adapter");
  return run(() =>
    acquisition.addSource({
      url,
      name: text(form, "name"),
      source_id: text(form, "source_id"),
      adapter:
        adapter === "web" || adapter === "local-folder" || adapter === "bibliographic"
          ? adapter
          : null,
      search: text(form, "search"),
      note: text(form, "note"),
      access: accessModel(text(form, "access")),
      roles: form.get("store_role") === "on" ? ["store-search-en"] : [],
      download_permitted: form.get("download_permitted") === "on",
      test: form.get("skip_test") !== "on",
    }),
  );
}

export async function sourceAction(
  _previous: ActionState | null,
  form: FormData,
): Promise<ActionState> {
  const id = text(form, "id");
  const action = text(form, "action");
  if (!id || !action) return { ok: false, message: "Missing source or action." };
  if (action !== "test" && action !== "enable" && action !== "disable" && action !== "remove") {
    return { ok: false, message: `Unknown action ${action}.` };
  }
  return run(() => acquisition.sourceAction(id, action));
}

/** Re-read the Vault and rebuild every document the screens show. */
export async function refreshDataAction(
  _previous: ActionState | null,
  _form: FormData,
): Promise<ActionState> {
  return run(() => acquisition.refresh());
}


export async function refreshIntakeAction(
  _previous: ActionState | null,
  _form: FormData,
): Promise<ActionState> {
  return run(() => acquisition.refreshIntake());
}

export async function refreshScaffoldAction(
  _previous: ActionState | null,
  _form: FormData,
): Promise<ActionState> {
  return run(async () => {
    const plan = await acquisition.refreshScaffold();
    const folders = plan.create.length;
    return {
      ok: plan.ran,
      message: plan.ran
        ? `${folders} folder${folders === 1 ? "" : "s"} are missing. Creating them stays a command you run.`
        : "Could not recompute the plan.",
      command: plan.command,
      output: plan.output,
    };
  });
}
