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
from continuum_imaging.stages import resize_exact

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
    DataClass,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)
from continuum_providers.policy import reference_data_class, transmission_refusal
from continuum_providers.stages import (
    PanelStageRequest,
    PanelStageResult,
    StageCapabilities,
    identity_evidence,
    scene_references,
)

__all__ = [
    "CORE_NODES",
    "IDENTITY_NODES",
    "STAGE_DENOISE",
    "STAGE_WORKFLOW_ID",
    "WORKFLOW_ID",
    "WORKFLOW_VERSION",
    "ComfyConfig",
    "ComfyModel",
    "ComfyPageProvider",
    "ComfyStatus",
    "Transport",
    "stage_workflow_manifest",
    "urllib_transport",
    "workflow_manifest",
]

WORKFLOW_ID = "continuum.comfy.page"
WORKFLOW_VERSION = "3"
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
    "lowres, bad anatomy, bad hands, text, letters, typography, Japanese characters, error, "
    "missing finger, extra digits, fewer digits, cropped, worst quality, low quality, low score, "
    "bad score, average score, signature, watermark, username, blurry, speech bubble, dialogue "
    "balloon, caption, sound effect text, logo, panel border, comic page, manga page, comic panel, "
    "multiple panels, split screen, collage, contact sheet, duplicate person, extra people"
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
    style_prompt: str = "anime screencap, clean lineart, expressive face, detailed background"
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


#: Layered construction on ComfyUI: every stage after the first starts from the
#: frozen upstream image as its initial latent, at a low denoise, so the stage adds
#: its layer without redrawing the structure it was given. No control net yet: the
#: upstream is held by the init latent only, and drift is measured on every result.
STAGE_WORKFLOW_ID = "continuum.comfy.panel-stage"
STAGE_WORKFLOW_VERSION = "2"
STAGE_DENOISE: dict[str, float] = {
    "DRAWING": 0.42,
    "LINE": 0.3,
    "VALUE_MATERIAL": 0.3,
    "LIGHT_SHADOW": 0.32,
    "FX": 0.38,
    "ENVIRONMENT_INTEGRATION": 0.3,
    "FINISH": 0.22,
}
#: How the scene lane is applied per purpose: IP-Adapter weight type and weight.
#: A separate adapter node from every identity lane, so setting and style are
#: never averaged into a character's identity.
SCENE_CONDITIONING: dict[str, tuple[str, float]] = {
    "COMPOSITION": ("composition", 0.8),
    "STYLE_AND_COMPOSITION": ("style and composition", 0.6),
    "STYLE": ("style transfer", 0.5),
}
STAGE_TAGS: dict[str, tuple[str, ...]] = {
    "COMPOSITION": ("clear composition", "readable silhouettes"),
    "DRAWING": ("detailed", "clean construction"),
    "LINE": ("clean lineart", "crisp contours"),
    "VALUE_MATERIAL": ("clear value masses", "material texture"),
    "LIGHT_SHADOW": ("dramatic lighting", "cast shadows"),
    "FX": ("visual effects",),
    "ENVIRONMENT_INTEGRATION": ("detailed background", "contact shadows"),
    "FINISH": ("high quality", "clean finish"),
}


def stage_workflow_manifest() -> dict[str, str]:
    templates = {
        "first_stage": _master_graph(),
        "later_stages": _color_graph(),
        "denoise": STAGE_DENOISE,
        "scene_conditioning": {key: list(value) for key, value in SCENE_CONDITIONING.items()},
        "tags": {key: list(value) for key, value in STAGE_TAGS.items()},
        "identity": list(IDENTITY_NODES),
    }
    digest = hashlib.sha256(json.dumps(templates, sort_keys=True).encode()).hexdigest()
    return {"id": STAGE_WORKFLOW_ID, "version": STAGE_WORKFLOW_VERSION, "sha256": digest}


def workflow_manifest() -> dict[str, str]:
    templates = {
        "master": _master_graph(),
        "color": "panel-composite-passthrough-v1",
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


_ANIMAGINE_TAG_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("wide", "establish"), "wide shot"),
    (("close-up", "close up", "medium-close", "medium close"), "close-up"),
    (("medium",), "medium shot"),
    (("reaction", "reacting", "reacts"), "reaction"),
    (("strike", "striking", "attack", "attacks"), "attacking"),
    (("impact",), "impact"),
    (("turns", "turning", "looks back"), "looking back"),
    (("carry", "carries", "carrying"), "carrying"),
    (("run", "running", "moving away"), "running"),
    (("barrier",), "energy barrier"),
    (("red",), "red energy"),
    (("blue",), "blue energy"),
    (("forest",), "forest"),
    (("village", "settlement"), "village"),
    (("inn",), "inn"),
    (("house", "houses"), "houses"),
    (("lake",), "lake"),
    (("path", "lane", "road"), "path"),
    (("hill",), "hill"),
    (("tree",), "tree"),
    (("guitar",), "guitar"),
    (("kitchen",), "kitchen"),
    (("table",), "table"),
    (("fire", "hearth"), "fire"),
    (("night",), "night"),
    (("sunset",), "sunset"),
    (("day", "morning"), "day"),
)


def _animagine_tags(text: str) -> list[str]:
    """Compile creator prose into the tag vocabulary Animagine was trained on."""
    lowered = text.lower()
    tags: list[str] = []
    for needles, tag in _ANIMAGINE_TAG_RULES:
        if any(needle in lowered for needle in needles):
            tags.append(tag)
    if any(token in lowered for token in ("no people", "environment only", "empty scene")):
        tags.extend(("scenery", "no humans"))
    if any(token in lowered for token in ("dynamic", "action", "impact", "strike", "attack")):
        tags.append("dynamic pose")
    if any(token in lowered for token in ("ordinary", "calm", "quiet", "domestic")):
        tags.append("natural pose")
    return list(dict.fromkeys(tags))


def _identity_reference_rank(reference: ArtworkReference) -> int:
    """Prioritize identity evidence while preserving source order within a tier."""
    provenance = reference.provenance or {}
    facets = {str(value).upper() for value in provenance.get("facets") or []}
    evidence_role = str(provenance.get("production_evidence_role") or "").upper()
    if evidence_role in {"IDENTITY", "FACE", "HAIR"} or facets & {"FACE", "HAIR", "IDENTITY"}:
        return 0
    if evidence_role == "BODY" or "BODY" in facets:
        return 1
    if facets & {"EXPRESSION", "POSE"}:
        return 2
    return 3


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
    for group in by_character.values():
        group.sort(key=_identity_reference_rank)

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

    def _panel_prompts(self, request: PageRenderRequest, panel: dict[str, Any]) -> tuple[str, str]:
        """Prompt one bounded illustration using Animagine's tag-first vocabulary."""
        page = request.page
        characters = [str(name) for name in panel.get("characters") or []]
        direction = str(panel.get("direction") or "").strip()
        shot = str(panel.get("shot") or "STANDARD").lower()
        creator_notes = str(request.settings.get("creator_notes") or "").strip()
        character_context = request.settings.get("character_context") or {}

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

        tags: list[str] = ["safe"]
        if len(characters) == 1:
            tags.append("solo")
        elif len(characters) > 1:
            tags.append("multiple people")
        else:
            tags.extend(("scenery", "no humans"))

        for name in characters:
            tags.append(name.lower())
            context = character_context.get(name) or {}
            source_label = str(context.get("source_label") or "").strip().lower()
            if source_label:
                tags.append(source_label)

        shot_tags = {
            "wide": "wide shot",
            "close": "close-up",
            "medium": "medium shot",
            "impact": "dynamic angle",
        }
        if shot in shot_tags:
            tags.append(shot_tags[shot])

        semantic_text = " ".join([direction, *relevant_locks[:3], creator_notes]).strip()
        tags.extend(_animagine_tags(semantic_text))
        tags.extend(tag.strip() for tag in self.config.style_prompt.split(",") if tag.strip())
        tags.extend(("masterpiece", "high score", "great score", "absurdres"))
        positive = ", ".join(dict.fromkeys(tag for tag in tags if tag))[:2400]

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
                    "combine_embeds": "average",
                    "start_at": 0.0,
                    "end_at": 0.85,
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
            panel_reference_limit = min(
                self.config.max_reference_images,
                max(0, len(character_names) * 3),
            )
            sent = (
                _select_identity_references(scoped, panel_reference_limit)
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
                "mode": (
                    "separate adapter chain per character; averaged refs; "
                    "max three refs per cast member"
                ),
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

    # -- layered construction -------------------------------------------------
    @property
    def stage_capabilities(self) -> StageCapabilities:
        status = self.status()
        return StageCapabilities(
            output=RenderOutput.ARTWORK_CANDIDATE,
            stages=frozenset({"COMPOSITION", *STAGE_DENOISE}),
            preserves_upstream=True,
            identity_conditioning=status.identity_conditioning,
            reference_conditioning=status.identity_conditioning,
            source_excerpts=(
                self.config.backend is not ArtworkBackendKind.COMFY_REMOTE
                or self.config.allow_source_excerpts
            ),
            seeded=True,
            max_edge=self.config.max_edge,
            available=status.ready,
            notes=(
                status.reason()
                if not status.ready
                else "later stages start from the frozen upstream as the initial latent "
                "(denoise <= 0.42); no control net"
            ),
        )

    def _stage_prompts(self, request: PanelStageRequest) -> tuple[str, str]:
        contract = request.contract
        cast = [str(name) for name in contract.get("cast") or []]
        tags: list[str] = ["safe"]
        if len(cast) == 1:
            tags.append("solo")
        elif cast:
            tags.append("multiple people")
        else:
            tags.extend(("scenery", "no humans"))
        tags.extend(name.lower() for name in cast)
        shot = str(contract.get("shot") or "").lower()
        tags.extend(
            {"wide": ["wide shot"], "close": ["close-up"], "medium": ["medium shot"]}.get(shot, [])
        )
        semantic = " ".join(
            [
                str(contract.get("beat") or ""),
                *[str(item) for item in (contract.get("required") or [])[:3]],
                str(request.settings.get("creator_notes") or ""),
            ]
        )
        tags.extend(_animagine_tags(semantic))
        tags.extend(STAGE_TAGS.get(request.stage, ()))
        tags.extend(t.strip() for t in self.config.style_prompt.split(",") if t.strip())
        tags.extend(("masterpiece", "high score", "great score", "absurdres"))
        positive = ", ".join(dict.fromkeys(tag for tag in tags if tag))[:2400]
        negatives = [BASE_NEGATIVE, NOISE_NEGATIVE]
        negatives.extend(str(item) for item in contract.get("forbidden") or [])
        return positive, ", ".join(item for item in negatives if item)[:3600]

    def render_stage(self, request: PanelStageRequest) -> PanelStageResult:
        """One construction stage of one panel, on the frozen upstream it was given."""
        status = self.status(refresh=True)
        if not status.ready:
            raise ProviderUnavailableError(
                status.reason(),
                remediation="Start ComfyUI (or the remote GPU session) and check the checkpoint.",
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )
        # Defense in depth: Continuum already withholds what this backend may not
        # receive; anything that still arrives is withheld here, never uploaded.
        withheld: list[dict[str, Any]] = []
        usable: list[ArtworkReference] = []
        for reference in request.references:
            reason = transmission_refusal(
                reference.provenance or {},
                self.descriptor.locality,
                source_excerpts_allowed=self.config.allow_source_excerpts,
            )
            if reason is None:
                usable.append(reference)
            else:
                withheld.append(
                    {
                        "reference_id": reference.reference_id,
                        "role": reference.role,
                        "reason": reason,
                    }
                )
        request = replace(request, references=tuple(usable))
        candidates = [
            r for r in request.references if (r.provenance or {}).get("status") == "CANDIDATE"
        ]
        identity = [
            r for r in request.references if identity_evidence(r) and r not in candidates
        ]
        cast = {str(name) for name in request.contract.get("cast") or []}
        ungrounded = sorted(cast - {str(r.character) for r in identity})
        if ungrounded:
            # Never draw a cast member from setting, style or technique images alone.
            raise ProviderUnavailableError(
                f"No identity evidence this backend may receive for {', '.join(ungrounded)}.",
                remediation="Confirm project-created references, or render on a local backend.",
                blocked_reason=BlockedReason.MISSING_SOURCE_ASSET.value,
                missing_safe_identity=ungrounded,
            )
        sent = (
            _select_identity_references(
                [r for r in identity if r.character in cast],
                min(self.config.max_reference_images, len(cast) * 3),
            )
            if status.identity_conditioning and cast
            else []
        )
        purpose, scene, not_conditioned = scene_references(request)
        if scene and not status.identity_conditioning:
            not_conditioned.extend(
                {
                    "reference_id": r.reference_id,
                    "role": r.role,
                    "reason": "this ComfyUI lacks the IP-Adapter nodes for image conditioning",
                }
                for r in scene
            )
            scene = []
        positive, negative = self._stage_prompts(request)
        denoise = STAGE_DENOISE.get(request.stage, 0.3)
        values: dict[str, Any] = {
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
            "denoise": denoise,
        }
        uploaded: dict[str, str] = {}
        if request.upstream is None:
            graph = _fill(_master_graph(), values)
            denoise_used = 1.0
        else:
            digest = _sha(request.upstream)
            values["master"] = self._upload(f"continuum-stage-{digest[:24]}.png", request.upstream)
            graph = _fill(_color_graph(), values)
            denoise_used = denoise
        scene_type, scene_weight = SCENE_CONDITIONING[purpose.value]
        if sent or scene:
            self._add_reference_lanes(graph, sent, scene, scene_type, scene_weight, uploaded)
        data = self._run(graph)
        produced = probe(data)
        width, height = produced.width, produced.height
        if request.upstream is not None:
            # A VAE round trip may snap edges to multiples of 8; restore the exact frozen
            # size. A larger difference is a moved geometry and is refused by the caller.
            upstream = probe(request.upstream)
            dx, dy = abs(width - upstream.width), abs(height - upstream.height)
            if dx <= 8 and dy <= 8:
                width, height = upstream.width, upstream.height
        encoded = resize_exact(data, width, height)
        return PanelStageResult(
            backend=self.config.backend,
            provider_id=self.config.provider_id,
            output=RenderOutput.ARTWORK_CANDIDATE,
            image=RenderedImage(encoded.data, encoded.mime, encoded.width, encoded.height),
            provenance={
                "backend": self.config.backend.value,
                "model": {
                    "name": self.config.model.name,
                    "version": self.config.model.version,
                    "sha256": self.config.model.sha256,
                    "license": self.config.model.license,
                    "source": self.config.model.source,
                },
                "workflow": stage_workflow_manifest(),
                "settings": {
                    "stage": request.stage,
                    "steps": self.config.steps,
                    "cfg": self.config.cfg,
                    "sampler": self.config.sampler,
                    "scheduler": self.config.scheduler,
                    "denoise": denoise_used,
                    "width": request.width,
                    "height": request.height,
                    "upstream_held_by": "init latent" if request.upstream is not None else None,
                    "positive": positive,
                    "negative": negative,
                    "lettering": "disabled; Continuum owns text after artwork",
                },
                "seed": request.seed,
                "conditioning": {
                    "identity": {
                        name: [r.reference_id for r in sent if r.character == name]
                        for name in sorted({str(r.character) for r in sent})
                    },
                    "scene": {
                        "purpose": purpose.value,
                        "mechanism": f"IP-Adapter weight_type={scene_type!r}",
                        "weight": scene_weight,
                        "references": [r.reference_id for r in scene],
                    }
                    if scene
                    else None,
                },
                "references_transmitted": [r.reference_id for r in [*scene, *sent]],
                "references_not_conditioned": not_conditioned,
                "references_withheld": withheld,
                "identity_references_sent": [r.reference_id for r in sent],
                "candidates_not_used_for_identity": [r.reference_id for r in candidates],
            },
        )

    def _add_reference_lanes(
        self,
        graph: dict[str, Any],
        identity: Sequence[ArtworkReference],
        scene: Sequence[ArtworkReference],
        scene_type: str,
        scene_weight: float,
        uploaded_cache: dict[str, str],
    ) -> None:
        """A scene lane and one identity lane per character, as separate adapters.

        The scene lane (setting, house style) is one IP-Adapter with a composition
        or style weight type; each named character then gets its own adapter. No
        image is ever in two lanes, and the scene lane never carries a character.
        """
        graph["20"] = {
            "class_type": "IPAdapterUnifiedLoader",
            "inputs": {"model": ["4", 0], "preset": self.config.ipadapter_preset},
        }
        model: list[Any] = ["20", 0]
        counters = {"load": 100, "batch": 300, "adapter": 500}

        def next_id(kind: str) -> str:
            counters[kind] += 1
            return str(counters[kind] - 1)

        def batch(group: Sequence[ArtworkReference]) -> list[Any]:
            images: list[list[Any]] = []
            for reference in group:
                digest = _sha(reference.data)
                name = uploaded_cache.get(digest)
                if name is None:
                    name = self._upload(f"continuum-{digest[:24]}.png", reference.data)
                    uploaded_cache[digest] = name
                node = next_id("load")
                graph[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
                images.append([node, 0])
            joined = images[0]
            for image in images[1:]:
                node = next_id("batch")
                graph[node] = {
                    "class_type": "ImageBatch",
                    "inputs": {"image1": joined, "image2": image},
                }
                joined = [node, 0]
            return joined

        def adapter(images: list[Any], weight: float, weight_type: str, end_at: float) -> None:
            nonlocal model
            node = next_id("adapter")
            graph[node] = {
                "class_type": "IPAdapterAdvanced",
                "inputs": {
                    "model": model,
                    "ipadapter": ["20", 1],
                    "image": images,
                    "weight": weight,
                    "weight_type": weight_type,
                    "combine_embeds": "average",
                    "start_at": 0.0,
                    "end_at": end_at,
                    "embeds_scaling": "V only",
                },
            }
            model = [node, 0]

        if scene:
            adapter(batch(scene), scene_weight, scene_type, 1.0)
        groups: dict[str, list[ArtworkReference]] = {}
        for reference in identity:
            if reference.character:
                groups.setdefault(reference.character, []).append(reference)
        identity_weight = self.config.ipadapter_weight / max(1.0, len(groups) ** 0.25)
        for group in groups.values():
            adapter(batch(group), identity_weight, "linear", 0.85)
        graph["3"]["inputs"]["model"] = model


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_source_excerpt(reference: ArtworkReference) -> bool:
    return reference_data_class(reference.provenance or {}) is DataClass.SOURCE_EXCERPT


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
