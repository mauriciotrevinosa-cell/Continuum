"""ComfyUI page backend: ``COMFY_LOCAL`` and ``COMFY_REMOTE``.

Only the materialized request for one page is sent to ComfyUI. Remote sessions
never receive the Vault itself or local file paths. Identity conditioning uses
confirmed references only, records exactly which references were sent, and
applies a deterministic per-character budget so one character cannot consume
all IP-Adapter slots on ensemble pages.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from continuum_core import ProviderUnavailableError
from continuum_core.jobstates import BlockedReason
from continuum_core.references import RenderOutput
from continuum_imaging import probe
from continuum_imaging.manga import bw_finish, compose_manga_page, panel_boxes

from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkCapabilities,
    ArtworkReference,
    PageRenderRequest,
    PageRenderResult,
    RenderedImage,
)
from continuum_providers.contracts import (
    Capability,
    CostClass,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)

__all__ = [
    "CORE_NODES",
    "IDENTITY_NODES",
    "WORKFLOW_ID",
    "WORKFLOW_VERSION",
    "ComfyConfig",
    "ComfyModel",
    "ComfyPageProvider",
    "ComfyStatus",
    "Transport",
    "urllib_transport",
    "workflow_manifest",
]

WORKFLOW_ID = "continuum.comfy.page"
WORKFLOW_VERSION = "2"
CORE_NODES = (
    "CheckpointLoaderSimple",
    "CLIPTextEncode",
    "EmptyLatentImage",
    "KSampler",
    "VAEDecode",
    "VAEEncode",
    "SaveImage",
    "LoadImage",
)
IDENTITY_NODES = ("IPAdapterUnifiedLoader", "IPAdapterAdvanced", "ImageBatch")
NOISE_NEGATIVE = "HUD, videogame UI, status window, stat screen, computer overlay, interface panel"
BASE_NEGATIVE = (
    "text, letters, typography, Japanese characters, speech bubble, dialogue balloon, caption, "
    "sound effect text, watermark, signature, logo, panel border, comic page, collage, contact "
    "sheet, duplicate person, extra people, lowres, blurry, deformed hands, extra fingers"
)

Transport = Callable[[str, str, bytes | None, dict[str, str]], tuple[int, bytes]]


def urllib_transport(timeout: float) -> Transport:
    def send(
        method: str, url: str, body: bytes | None, headers: dict[str, str]
    ) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, method=method, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read()

    return send


@dataclass(frozen=True, slots=True)
class ComfyModel:
    name: str
    version: str = ""
    sha256: str = ""
    license: str = ""
    source: str = ""

    def missing(self) -> list[str]:
        return [
            key
            for key in ("name", "version", "sha256", "license", "source")
            if not getattr(self, key)
        ]


@dataclass(frozen=True, slots=True)
class ComfyConfig:
    backend: ArtworkBackendKind
    base_url: str
    model: ComfyModel
    steps: int = 28
    cfg: float = 6.0
    sampler: str = "euler_ancestral"
    scheduler: str = "normal"
    color_denoise: float = 0.45
    style_prompt: str = "manga page, clean ink linework, expressive faces"
    ipadapter_preset: str = "PLUS (high strength)"
    ipadapter_weight: float = 0.8
    max_reference_images: int = 12
    max_edge: int = 2048
    timeout_seconds: float = 900.0
    poll_seconds: float = 1.0
    allow_source_excerpts: bool = False

    @property
    def provider_id(self) -> str:
        return "comfy.remote" if self.backend is ArtworkBackendKind.COMFY_REMOTE else "comfy.local"


@dataclass(slots=True)
class ComfyStatus:
    kind: str
    provider_id: str
    configured: bool
    endpoint: str
    reachable: bool = False
    error: str = ""
    missing_nodes: list[str] = field(default_factory=list)
    checkpoint_available: bool = False
    checkpoints_listed: int = 0
    identity_conditioning: bool = False
    model: dict[str, str] = field(default_factory=dict)
    model_metadata_missing: list[str] = field(default_factory=list)
    workflow: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.reachable and not self.missing_nodes and self.checkpoint_available

    def reason(self) -> str:
        if not self.configured:
            return f"{self.kind} is not configured"
        if not self.reachable:
            return f"{self.kind} is not reachable at {self.endpoint}: {self.error or 'no response'}"
        if self.missing_nodes:
            return f"{self.kind} lacks ComfyUI nodes: {', '.join(self.missing_nodes)}"
        if not self.checkpoint_available:
            return f"{self.kind} does not list the configured checkpoint {self.model.get('name')!r}"
        return "ready"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "provider_id": self.provider_id,
            "configured": self.configured,
            "endpoint": self.endpoint,
            "reachable": self.reachable,
            "ready": self.ready,
            "reason": self.reason(),
            "error": self.error,
            "missing_nodes": self.missing_nodes,
            "checkpoint_available": self.checkpoint_available,
            "checkpoints_listed": self.checkpoints_listed,
            "identity_conditioning": self.identity_conditioning,
            "model": self.model,
            "model_metadata_missing": self.model_metadata_missing,
            "workflow": self.workflow,
        }


def _master_graph() -> dict[str, Any]:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "$checkpoint"}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$positive", "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "$negative", "clip": ["4", 1]}},
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": "$width", "height": "$height", "batch_size": 1},
        },
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "$seed",
                "steps": "$steps",
                "cfg": "$cfg",
                "sampler_name": "$sampler",
                "scheduler": "$scheduler",
                "denoise": 1.0,
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["5", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "continuum_master", "images": ["8", 0]},
        },
    }


def _color_graph() -> dict[str, Any]:
    return {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "$checkpoint"}},
        "10": {"class_type": "LoadImage", "inputs": {"image": "$master"}},
        "11": {"class_type": "VAEEncode", "inputs": {"pixels": ["10", 0], "vae": ["4", 2]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "$positive", "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "$negative", "clip": ["4", 1]}},
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "$seed",
                "steps": "$steps",
                "cfg": "$cfg",
                "sampler_name": "$sampler",
                "scheduler": "$scheduler",
                "denoise": "$denoise",
                "model": ["4", 0],
                "positive": ["6", 0],
                "negative": ["7", 0],
                "latent_image": ["11", 0],
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"filename_prefix": "continuum_color", "images": ["8", 0]},
        },
    }


def workflow_manifest() -> dict[str, str]:
    templates = {
        "master": _master_graph(),
        "color": _color_graph(),
        "identity": list(IDENTITY_NODES),
        "composition": "deterministic-panel-first-v1",
    }
    digest = hashlib.sha256(json.dumps(templates, sort_keys=True).encode()).hexdigest()
    return {"id": WORKFLOW_ID, "version": WORKFLOW_VERSION, "sha256": digest}


def _fill(graph: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str) and node.startswith("$"):
            return values[node[1:]]
        return node

    filled: dict[str, Any] = walk(graph)
    return filled


def _select_identity_references(
    references: Sequence[ArtworkReference], limit: int
) -> list[ArtworkReference]:
    """Spend a finite IP-Adapter budget fairly across named characters.

    Preserve source order within each character. First give every named
    character one slot, then include unassigned continuity anchors, then spend
    remaining slots round-robin. This makes ensemble pages deterministic and
    prevents the first character's six observations from starving everyone
    later in the cast list.
    """
    if limit <= 0:
        return []

    by_character: dict[str, list[ArtworkReference]] = {}
    unassigned: list[ArtworkReference] = []
    for reference in references:
        if reference.character:
            by_character.setdefault(reference.character, []).append(reference)
        else:
            unassigned.append(reference)

    selected: list[ArtworkReference] = []
    offsets = dict.fromkeys(by_character, 0)

    for name, group in by_character.items():
        if len(selected) >= limit:
            return selected
        if group:
            selected.append(group[0])
            offsets[name] = 1

    for reference in unassigned:
        if len(selected) >= limit:
            return selected
        selected.append(reference)

    while len(selected) < limit:
        advanced = False
        for name, group in by_character.items():
            offset = offsets[name]
            if offset >= len(group):
                continue
            selected.append(group[offset])
            offsets[name] = offset + 1
            advanced = True
            if len(selected) >= limit:
                break
        if not advanced:
            break
    return selected


class ComfyPageProvider:
    """A ComfyUI server as a page backend."""

    STATUS_TTL_SECONDS = 30.0

    def __init__(self, config: ComfyConfig, transport: Transport | None = None) -> None:
        self.config = config
        self.backend = config.backend
        self.transport = transport or urllib_transport(min(60.0, config.timeout_seconds))
        self._status: ComfyStatus | None = None
        self._status_at = 0.0
        remote = config.backend is ArtworkBackendKind.COMFY_REMOTE
        self.descriptor = ProviderDescriptor(
            id=config.provider_id,
            capabilities=frozenset({Capability.PAGE_RENDER}),
            locality=Locality.REMOTE if remote else Locality.LOCAL,
            cost_class=CostClass.FREE,
            privacy_class=PrivacyClass.THIRD_PARTY if remote else PrivacyClass.SELF_HOSTED,
            model_ref=config.model.name or None,
            version=WORKFLOW_VERSION,
            license_note=config.model.license or "checkpoint license not recorded",
            rough_output=RenderOutput.ARTWORK_CANDIDATE,
        )

    def _url(self, path: str, query: dict[str, str] | None = None) -> str:
        base = self.config.base_url.rstrip("/")
        return f"{base}{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")

    def _endpoint(self) -> str:
        parsed = urllib.parse.urlparse(self.config.base_url)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else self.config.base_url

    def _json(self, method: str, path: str, payload: Any | None = None) -> Any:
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        status, data = self.transport(method, self._url(path), body, headers)
        if status >= 400:
            raise ProviderUnavailableError(
                f"ComfyUI answered {status} to {path}.",
                technical_detail=data[:500].decode("utf-8", "replace"),
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )
        return json.loads(data or b"null")

    def status(self, *, refresh: bool = False) -> ComfyStatus:
        now = time.monotonic()
        if (
            not refresh
            and self._status is not None
            and now - self._status_at < self.STATUS_TTL_SECONDS
        ):
            return self._status
        status = ComfyStatus(
            kind=self.config.backend.value,
            provider_id=self.config.provider_id,
            configured=bool(self.config.base_url),
            endpoint=self._endpoint(),
            model={
                "name": self.config.model.name,
                "version": self.config.model.version,
                "sha256": self.config.model.sha256,
                "license": self.config.model.license,
                "source": self.config.model.source,
            },
            model_metadata_missing=self.config.model.missing(),
            workflow=workflow_manifest(),
        )
        if status.configured:
            try:
                info = self._json("GET", "/object_info")
                status.reachable = True
                nodes = set(info or {})
                status.missing_nodes = [node for node in CORE_NODES if node not in nodes]
                status.identity_conditioning = all(node in nodes for node in IDENTITY_NODES)
                listed = (
                    ((info.get("CheckpointLoaderSimple") or {}).get("input") or {}).get("required")
                    or {}
                ).get("ckpt_name") or [[]]
                names = listed[0] if listed and isinstance(listed[0], list) else []
                status.checkpoints_listed = len(names)
                status.checkpoint_available = (
                    bool(self.config.model.name) and self.config.model.name in names
                )
            except (OSError, ValueError, ProviderUnavailableError) as exc:
                status.reachable = False
                status.error = type(exc).__name__ + (f": {exc}" if str(exc) else "")
        self._status, self._status_at = status, now
        return status

    @property
    def capabilities(self) -> ArtworkCapabilities:
        status = self.status()
        return ArtworkCapabilities(
            output=RenderOutput.ARTWORK_CANDIDATE,
            available=status.ready,
            max_reference_images=(
                self.config.max_reference_images if status.identity_conditioning else 0
            ),
            identity_conditioning=status.identity_conditioning,
            layout_conditioning=False,
            sibling_finishes=True,
            renders_text=False,
            seeded=True,
            max_edge=self.config.max_edge,
            notes=status.reason(),
        )

    def _upload(self, name: str, data: bytes) -> str:
        boundary = uuid.uuid4().hex
        parts = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n".encode(),
            data,
            f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="overwrite"\r\n\r\ntrue'
            f"\r\n--{boundary}--\r\n".encode(),
        ]
        status, body = self.transport(
            "POST",
            self._url("/upload/image"),
            b"".join(parts),
            {"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        if status >= 400:
            raise ProviderUnavailableError(
                "ComfyUI refused a reference upload.",
                technical_detail=body[:300].decode("utf-8", "replace"),
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )
        return str(json.loads(body).get("name") or name)

    def _run(self, graph: dict[str, Any]) -> bytes:
        queued = self._json("POST", "/prompt", {"prompt": graph, "client_id": "continuum"})
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise ProviderUnavailableError(
                "ComfyUI did not queue the workflow.",
                technical_detail=json.dumps(queued)[:500],
                blocked_reason=BlockedReason.MISSING_MODEL.value,
            )
        deadline = time.monotonic() + self.config.timeout_seconds
        while True:
            history = self._json("GET", f"/history/{urllib.parse.quote(prompt_id)}") or {}
            entry = history.get(prompt_id)
            if entry:
                state = (entry.get("status") or {}).get("status_str")
                if state == "error":
                    raise ProviderUnavailableError(
                        "ComfyUI failed to run the page workflow.",
                        technical_detail=json.dumps(entry.get("status"))[:800],
                        blocked_reason=BlockedReason.MISSING_MODEL.value,
                    )
                for output in (entry.get("outputs") or {}).values():
                    for image in output.get("images") or []:
                        query = {
                            "filename": str(image.get("filename", "")),
                            "subfolder": str(image.get("subfolder", "")),
                            "type": str(image.get("type", "output")),
                        }
                        status, data = self.transport("GET", self._url("/view", query), None, {})
                        if status < 400 and data:
                            return data
            if time.monotonic() > deadline:
                raise ProviderUnavailableError(
                    "ComfyUI did not finish the page in time.",
                    remediation="The GPU session may be busy or gone; the attempt can be retried.",
                    blocked_reason=BlockedReason.RESOURCE_UNAVAILABLE.value,
                )
            time.sleep(self.config.poll_seconds)

    def _panel_prompts(
        self, request: PageRenderRequest, panel: dict[str, Any]
    ) -> tuple[str, str]:
        """Prompt one panel only; Continuum owns page layout and lettering."""
        page = request.page
        characters = [str(name) for name in panel.get("characters") or []]
        names = ", ".join(characters)
        direction = str(panel.get("direction") or "").strip()
        shot = str(panel.get("shot") or "STANDARD").lower()
        brief = str(request.settings.get("brief") or "").strip()

        context = next(
            (
                str(item).strip()
                for item in page.get("directions") or []
                if str(item).strip()
                and not str(item).startswith("PAGE CONSTRUCTION:")
                and not str(item).startswith("MUST SHOW:")
            ),
            "",
        )
        locks = [
            str(item).removeprefix("MUST SHOW:").strip()
            for item in page.get("directions") or []
            if str(item).startswith("MUST SHOW:")
        ]
        relevant_locks = [
            lock
            for lock in locks
            if not characters or any(name.lower() in lock.lower() for name in characters)
        ]
        if not relevant_locks:
            relevant_locks = locks[:2]

        positive_parts = [
            "single Japanese manga panel illustration",
            "clean intentional ink contours",
            "manga-ready anatomy and facial construction",
            "restrained cel shading, controlled values, readable silhouette",
            "no lettering; leave clean negative space for later typography",
            f"{shot} shot",
            f"characters: {names}" if names else "environment only; no people",
            f"panel action: {direction}",
            f"scene context: {context}" if context and context != direction else "",
            "required: " + "; ".join(relevant_locks[:3]) if relevant_locks else "",
        ]
        if brief and brief not in direction and brief not in context:
            positive_parts.append(f"creator correction: {brief}")
        positive = ". ".join(part for part in positive_parts if part)[:3600]

        negatives = [BASE_NEGATIVE, NOISE_NEGATIVE]
        negatives.extend(str(item) for item in page.get("constraints") or [])
        rules = request.continuity.get("character_rules") or {}
        for name in characters:
            rule = rules.get(name) or {}
            negatives.extend(str(item) for item in rule.get("forbidden_accessories") or [])
        return positive, ", ".join(item for item in negatives if item)[:3600]

    @staticmethod
    def _panel_size(
        request: PageRenderRequest, box: tuple[float, float, float, float]
    ) -> tuple[int, int]:
        """A T4-friendly latent size matching the panel aspect ratio."""
        _x, _y, width_share, height_share = box
        target_w = max(1, int(request.width * width_share))
        target_h = max(1, int(request.height * height_share))
        scale = min(1.0, 1024 / max(target_w, target_h))
        width = max(512, int(target_w * scale))
        height = max(512, int(target_h * scale))
        width = max(512, round(width / 64) * 64)
        height = max(512, round(height / 64) * 64)
        return min(width, 1024), min(height, 1024)

    def _add_identity_chain(
        self,
        graph: dict[str, Any],
        references: Sequence[ArtworkReference],
        uploaded_cache: dict[str, str],
    ) -> None:
        """Apply each character's refs through its own adapter stage.

        A single ImageBatch containing several people tells IP-Adapter to blend
        identities. Chaining one adapter per named character keeps evidence
        grouped even when two characters share a panel.
        """
        groups: dict[str, list[ArtworkReference]] = {}
        for reference in references:
            if reference.character:
                groups.setdefault(reference.character, []).append(reference)
        if not groups:
            return

        graph["20"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["4", 0], "preset": self.config.ipadapter_preset},
        }
        model: list[Any] = ["20", 0]
        load_node = 100
        batch_node = 300
        adapter_node = 500
        weight = self.config.ipadapter_weight / max(1.0, len(groups) ** 0.25)

        for _character, group in groups.items():
            image_nodes: list[list[Any]] = []
            for reference in group:
                digest = _sha(reference.data)
                uploaded = uploaded_cache.get(digest)
                if uploaded is None:
                    uploaded = self._upload(f"continuum-{digest[:24]}.png", reference.data)
                    uploaded_cache[digest] = uploaded
                node = str(load_node)
                load_node += 1
                graph[node] = {"class_type": "LoadImage", "inputs": {"image": uploaded}}
                image_nodes.append([node, 0])

            batch = image_nodes[0]
            for image_node in image_nodes[1:]:
                node = str(batch_node)
                batch_node += 1
                graph[node] = {
                    "class_type": "ImageBatch",
                    "inputs": {"image1": batch, "image2": image_node},
                }
                batch = [node, 0]

            node = str(adapter_node)
            adapter_node += 1
            graph[node] = {
                "class_type": "IPAdapterAdvanced",
                "inputs": {
                    "model": model,
                    "ipadapter": ["20", 1],
                    "image": batch,
                    "weight": weight,
                    "weight_type": "linear",
                    "combine_embeds": "concat",
                    "start_at": 0.0,
                    "end_at": 1.0,
                    "embeds_scaling": "V only",
                },
            }
            model = [node, 0]
        graph["3"]["inputs"]["model"] = model

    def render_page(self, request: PageRenderRequest) -> PageRenderResult:
        status = self.status(refresh=True)
        if not status.ready:
            raise ProviderUnavailableError(
                status.reason(),
                remediation="Start ComfyUI (or the remote GPU session) and check the checkpoint.",
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )

        candidates = [
            reference
            for reference in request.references
            if (reference.provenance or {}).get("status") == "CANDIDATE"
        ]
        identity = [
            reference
            for reference in request.references
            if reference.role in {"CANON", "CONTINUITY"} and reference not in candidates
        ]
        if (
            self.config.backend is ArtworkBackendKind.COMFY_REMOTE
            and not self.config.allow_source_excerpts
        ):
            excerpts = [reference for reference in identity if _is_source_excerpt(reference)]
            if excerpts:
                raise ProviderUnavailableError(
                    f"The page bundle holds {len(excerpts)} source manga excerpt(s); the remote "
                    "backend may not receive them.",
                    remediation="Confirm project-created references instead, render locally, or "
                    "explicitly allow source excerpts for the remote backend in settings.",
                    blocked_reason=BlockedReason.MISSING_PROVIDER.value,
                )

        panels = list(request.plan.get("render_panels") or [])
        if not panels:
            panels = [
                {
                    "number": 1,
                    "direction": " ".join(
                        str(item) for item in request.page.get("directions") or []
                    ),
                    "characters": list(request.page.get("characters") or []),
                    "shot": "STANDARD",
                    "emphasis": "NORMAL",
                }
            ]
        boxes = panel_boxes(len(panels))
        uploaded_cache: dict[str, str] = {}
        panel_masters: list[bytes] = []
        panel_records: list[dict[str, Any]] = []
        used_reference_ids: list[str] = []
        first_positive = ""
        first_negative = ""

        for index, (panel, box) in enumerate(zip(panels, boxes, strict=True)):
            character_names = {str(name) for name in panel.get("characters") or []}
            scoped = [
                reference
                for reference in identity
                if reference.character is not None and reference.character in character_names
            ]
            sent = (
                _select_identity_references(scoped, self.config.max_reference_images)
                if status.identity_conditioning
                else []
            )
            positive, negative = self._panel_prompts(request, panel)
            if index == 0:
                first_positive, first_negative = positive, negative
            width, height = self._panel_size(request, box)
            panel_seed = request.seed + index * 1009
            values = {
                "checkpoint": self.config.model.name,
                "positive": positive,
                "negative": negative,
                "width": width,
                "height": height,
                "seed": panel_seed,
                "steps": self.config.steps,
                "cfg": self.config.cfg,
                "sampler": self.config.sampler,
                "scheduler": self.config.scheduler,
                "denoise": self.config.color_denoise,
            }
            graph = _fill(_master_graph(), values)
            if sent:
                self._add_identity_chain(graph, sent, uploaded_cache)
            rendered = self._run(graph)
            panel_masters.append(rendered)
            used_reference_ids.extend(reference.reference_id for reference in sent)
            panel_records.append(
                {
                    "number": panel.get("number", index + 1),
                    "direction": panel.get("direction", ""),
                    "characters": sorted(character_names),
                    "shot": panel.get("shot", "STANDARD"),
                    "seed": panel_seed,
                    "render_size": [width, height],
                    "identity_references": [reference.reference_id for reference in sent],
                }
            )

        composite = compose_manga_page(panel_masters, request.width, request.height)
        master_image = RenderedImage(
            composite.data, composite.mime, composite.width, composite.height
        )
        bw = bw_finish(composite.data)
        # Color is deliberately the panel composite, not a whole-page img2img pass:
        # re-diffusing the complete page was mutating faces, layouts and text.
        color_image = RenderedImage(
            composite.data, composite.mime, composite.width, composite.height
        )
        used = set(used_reference_ids)
        settings = {
            "steps": self.config.steps,
            "cfg": self.config.cfg,
            "sampler": self.config.sampler,
            "scheduler": self.config.scheduler,
            "width": request.width,
            "height": request.height,
            "panel_first": True,
            "panel_count": len(panels),
            "lettering": "disabled; Continuum owns text after artwork",
            "ipadapter": {
                "preset": self.config.ipadapter_preset,
                "weight": self.config.ipadapter_weight,
                "mode": "separate adapter chain per character per panel",
            },
            "positive_example": first_positive,
            "negative": first_negative,
            **{
                key: value
                for key, value in request.settings.items()
                if key not in {"positive", "negative"}
            },
        }
        return PageRenderResult(
            backend=self.config.backend,
            provider_id=self.config.provider_id,
            output=RenderOutput.ARTWORK_CANDIDATE,
            master=master_image,
            bw=RenderedImage(bw.data, bw.mime, bw.width, bw.height),
            color=color_image,
            provenance={
                "backend": self.config.backend.value,
                "model": {
                    "name": self.config.model.name,
                    "version": self.config.model.version,
                    "sha256": self.config.model.sha256,
                    "license": self.config.model.license,
                    "source": self.config.model.source,
                    "role": "panel image support; Continuum owns sequencing and composition",
                },
                "workflow": workflow_manifest(),
                "settings": settings,
                "seed": request.seed,
                "master_sha256": master_image.sha256,
                "panel_renders": panel_records,
                "identity_references_sent": list(dict.fromkeys(used_reference_ids)),
                "candidates_not_used_for_identity": [
                    reference.reference_id for reference in candidates
                ],
                "references_not_used_by_this_workflow": [
                    reference.reference_id
                    for reference in request.references
                    if reference.reference_id not in used
                ],
                "bw_finish": "line-preserving continuum_imaging.manga.bw_finish",
                "color_finish": "deterministic panel composite; no whole-page re-diffusion",
            },
        )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_source_excerpt(reference: ArtworkReference) -> bool:
    provenance = reference.provenance or {}
    return (
        provenance.get("authority") in {"PRIMARY_SOURCE", "OFFICIAL"}
        or provenance.get("origin") in {"SOURCE", "OFFICIAL_ART", "FAN_ART"}
        or provenance.get("kind") == "source_page"
    )


def configured_providers(settings: Any) -> list[ComfyPageProvider]:
    """The ComfyUI backends the settings configure - none when unset."""
    model = ComfyModel(
        name=str(getattr(settings, "comfy_checkpoint", "") or ""),
        version=str(getattr(settings, "comfy_checkpoint_version", "") or ""),
        sha256=str(getattr(settings, "comfy_checkpoint_sha256", "") or ""),
        license=str(getattr(settings, "comfy_checkpoint_license", "") or ""),
        source=str(getattr(settings, "comfy_checkpoint_source", "") or ""),
    )
    base = ComfyConfig(
        backend=ArtworkBackendKind.COMFY_LOCAL,
        base_url="",
        model=model,
        timeout_seconds=float(getattr(settings, "comfy_timeout_seconds", 900.0)),
    )
    out: list[ComfyPageProvider] = []
    local = str(getattr(settings, "comfy_local_url", "") or "")
    remote = str(getattr(settings, "comfy_remote_url", "") or "")
    if local:
        out.append(ComfyPageProvider(replace(base, base_url=local)))
    if remote:
        out.append(
            ComfyPageProvider(
                replace(
                    base,
                    backend=ArtworkBackendKind.COMFY_REMOTE,
                    base_url=remote,
                    allow_source_excerpts=bool(
                        getattr(settings, "comfy_remote_allow_source_excerpts", False)
                    ),
                )
            )
        )
    return out
