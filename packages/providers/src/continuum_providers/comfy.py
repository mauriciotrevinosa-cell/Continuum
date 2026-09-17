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
from continuum_imaging.manga import bw_finish

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
WORKFLOW_VERSION = "1"
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
    "text, letters, watermark, signature, logo, lowres, blurry, deformed hands, extra fingers"
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
    offsets = {name: 0 for name in by_character}

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

    def _prompts(self, request: PageRenderRequest) -> tuple[str, str]:
        page = request.page
        names = ", ".join(page.get("characters") or [])
        directions = " ".join(str(item) for item in page.get("directions") or [])
        brief = str(request.settings.get("brief") or "").strip()
        positive_parts = [self.config.style_prompt, names, directions]
        if brief and brief not in directions:
            positive_parts.append(f"CREATOR DIRECTION: {brief}")
        positive = ". ".join(part for part in positive_parts if part)[:3600]

        negatives = [BASE_NEGATIVE, NOISE_NEGATIVE]
        negatives.extend(str(item) for item in page.get("constraints") or [])
        for rule in (request.continuity.get("character_rules") or {}).values():
            negatives.extend(str(item) for item in rule.get("forbidden_accessories") or [])
        return positive, ", ".join(item for item in negatives if item)[:3600]

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

        sent = (
            _select_identity_references(identity, self.config.max_reference_images)
            if status.identity_conditioning
            else []
        )
        positive, negative = self._prompts(request)
        values = {
            "checkpoint": self.config.model.name,
            "positive": positive,
            "negative": negative,
            "width": request.width,
            "height": request.height,
            "seed": request.seed,
            "steps": self.config.steps,
            "cfg": self.config.cfg,
            "sampler": self.config.sampler,
            "scheduler": self.config.scheduler,
            "denoise": self.config.color_denoise,
        }
        graph = _fill(_master_graph(), values)
        if sent:
            uploaded = [
                self._upload(f"continuum-{_sha(reference.data)[:24]}.png", reference.data)
                for reference in sent
            ]
            graph["20"] = {
                "class_type": "IPAdapterUnifiedLoader",
                "inputs": {"model": ["4", 0], "preset": self.config.ipadapter_preset},
            }
            for index, name in enumerate(uploaded):
                graph[f"3{index}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
            batch = ["30", 0]
            for index in range(1, len(uploaded)):
                graph[f"4{index}"] = {
                    "class_type": "ImageBatch",
                    "inputs": {"image1": batch, "image2": [f"3{index}", 0]},
                }
                batch = [f"4{index}", 0]
            graph["21"] = {
                "class_type": "IPAdapterAdvanced",
                "inputs": {
                    "model": ["20", 0],
                    "ipadapter": ["20", 1],
                    "image": batch,
                    "weight": self.config.ipadapter_weight,
                    "weight_type": "linear",
                    "combine_embeds": "concat",
                    "start_at": 0.0,
                    "end_at": 1.0,
                    "embeds_scaling": "V only",
                },
            }
            graph["3"]["inputs"]["model"] = ["21", 0]

        master = self._run(graph)
        master_info = probe(master)
        master_name = self._upload(f"continuum-master-{_sha(master)[:24]}.png", master)
        color = self._run(_fill(_color_graph(), {**values, "master": master_name}))
        color_info = probe(color)
        bw = bw_finish(master)
        master_image = RenderedImage(
            master, master_info.mime, master_info.width, master_info.height
        )
        settings = {
            "steps": self.config.steps,
            "cfg": self.config.cfg,
            "sampler": self.config.sampler,
            "scheduler": self.config.scheduler,
            "color_denoise": self.config.color_denoise,
            "width": request.width,
            "height": request.height,
            "ipadapter": (
                {"preset": self.config.ipadapter_preset, "weight": self.config.ipadapter_weight}
                if sent
                else None
            ),
            "positive": positive,
            "negative": negative,
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
            color=RenderedImage(color, color_info.mime, color_info.width, color_info.height),
            provenance={
                "backend": self.config.backend.value,
                "model": {
                    "name": self.config.model.name,
                    "version": self.config.model.version,
                    "sha256": self.config.model.sha256,
                    "license": self.config.model.license,
                    "source": self.config.model.source,
                },
                "workflow": workflow_manifest(),
                "settings": settings,
                "seed": request.seed,
                "master_sha256": master_image.sha256,
                "identity_references_sent": [reference.reference_id for reference in sent],
                "candidates_not_used_for_identity": [
                    reference.reference_id for reference in candidates
                ],
                "references_not_used_by_this_workflow": [
                    reference.reference_id
                    for reference in request.references
                    if reference not in sent
                ],
                "bw_finish": "continuum_imaging.manga.bw_finish over the master",
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
