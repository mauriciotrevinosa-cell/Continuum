"""A paid image provider behind Continuum's own boundary (M3).

Continuum stays the author. This provider receives a materialized request -
prompt, references, seed, size - and returns pixels. It does not choose
references, does not read the Vault, does not decide what a panel means and
never becomes "the brain". Everything it is told was decided upstream.

What makes it safe to have at all:

* it is registered **only** when the creator has configured a key, an endpoint
  and at least one model. Nothing is reachable by default;
* it declares ``CostClass.PAID``, so the spend policy - not this module -
  decides whether it may ever be selected, and the ledger decides whether this
  particular request fits under what is left;
* model names are configuration, never literals here, so tiers can be swapped
  when a vendor renames them without touching a line of engine code;
* it refuses a request carrying a verbatim source excerpt, exactly as any
  remote provider does.

Two tiers are configurable - a cheap one for exploration and comparison, a
better one for the few artifacts everything else is built on. Which tier a
request uses is the caller's decision and is recorded with the result.
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from continuum_core import ProviderUnavailableError
from continuum_core.jobstates import BlockedReason
from continuum_core.references import RenderOutput
from continuum_imaging import probe

from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkReference,
    CharacterSheetRequest,
    CharacterSheetResult,
    RenderedImage,
)
from continuum_providers.contracts import (
    Capability,
    CostClass,
    DataClass,
    GenerationRequest,
    GenerationResult,
    Locality,
    PrivacyClass,
    ProviderDescriptor,
)
from continuum_providers.policy import reference_data_class
from continuum_providers.stages import (
    PanelStageRequest,
    PanelStageResult,
    StageCapabilities,
    identity_evidence,
    scene_references,
)

__all__ = [
    "GOOGLE_PROVIDER_ID",
    "GoogleImageConfig",
    "GoogleImageProvider",
    "ImageTier",
    "configured_google_provider",
    "google_image_config",
]

Transport = Callable[[str, str, bytes | None, dict[str, str]], tuple[int, bytes]]

GOOGLE_PROVIDER_ID = "google.image"
WORKFLOW_ID = "continuum.google.image"
WORKFLOW_VERSION = "1"


class ImageTier:
    """Which configured model a request asks for."""

    CHEAP = "CHEAP"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class GoogleImageConfig:
    """Everything about the provider that is configuration, not code."""

    endpoint: str
    api_key: str
    #: tier -> model identifier, exactly as the vendor names it. Configured.
    models: dict[str, str]
    #: The method appended to the model in the URL, e.g. ``<base>/<model>:<action>``.
    #: Configurable so a REST rename does not need a code change.
    action: str = "generateContent"
    #: Merged over the request's own generation config, last word to the creator.
    generation_config: dict[str, Any] = field(default_factory=dict)
    license_note: str = ""
    model_source: str = ""
    timeout_seconds: float = 120.0
    max_edge: int = 2048
    max_reference_images: int = 6

    def model_for(self, tier: str) -> str:
        return self.models.get(tier) or self.models.get(ImageTier.CHEAP) or ""

    @property
    def configured(self) -> bool:
        """Everything but the key has a default, so the key is what is missing."""
        return bool(self.endpoint and self.api_key and any(self.models.values()))

    def missing(self) -> list[str]:
        """What the creator still has to supply, named as environment variables."""
        gaps = []
        if not self.api_key:
            gaps.append("CONTINUUM_GOOGLE_API_KEY")
        if not self.endpoint:
            gaps.append("CONTINUUM_GOOGLE_IMAGE_ENDPOINT")
        if not any(self.models.values()):
            gaps.append("CONTINUUM_GOOGLE_IMAGE_MODEL_HIGH")
        return gaps


def _urllib_transport(timeout: float) -> Transport:
    import urllib.error
    import urllib.request

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


class GoogleImageProvider:
    """A configured paid image endpoint, behind Continuum's provider contracts."""

    backend = ArtworkBackendKind.TEST  # not a ComfyUI backend; kept for the union

    def __init__(self, config: GoogleImageConfig, transport: Transport | None = None) -> None:
        self.config = config
        self.transport = transport or _urllib_transport(config.timeout_seconds)
        self.descriptor = ProviderDescriptor(
            id=GOOGLE_PROVIDER_ID,
            capabilities=frozenset(
                {
                    Capability.IMAGE_GENERATE,
                    Capability.CHARACTER_MODEL_RENDER,
                    Capability.PANEL_STAGE_RENDER,
                }
            ),
            locality=Locality.REMOTE,
            cost_class=CostClass.PAID,
            privacy_class=PrivacyClass.THIRD_PARTY,
            model_ref=config.model_for(ImageTier.CHEAP) or None,
            version=WORKFLOW_VERSION,
            license_note=config.license_note or "vendor terms not recorded",
            rough_output=RenderOutput.ARTWORK_CANDIDATE,
            requirements={
                "api_key": True,
                "tiers": sorted(k for k, v in config.models.items() if v),
            },
        )

    # -- capabilities ---------------------------------------------------------
    @property
    def stage_capabilities(self) -> StageCapabilities:
        return StageCapabilities(
            output=RenderOutput.ARTWORK_CANDIDATE,
            stages=frozenset(
                {
                    "COMPOSITION",
                    "DRAWING",
                    "LINE",
                    "VALUE_MATERIAL",
                    "LIGHT_SHADOW",
                    "FX",
                    "ENVIRONMENT_INTEGRATION",
                    "FINISH",
                }
            ),
            preserves_upstream=True,
            identity_conditioning=True,
            reference_conditioning=True,
            #: A remote third party never receives verbatim source material.
            source_excerpts=False,
            seeded=True,
            max_edge=self.config.max_edge,
            available=self.config.configured,
            notes=(
                "reference images are attached to the request; the upstream is attached "
                "as the image to continue from"
                if self.config.configured
                else "the paid image provider is not configured"
            ),
        )

    # -- transport ------------------------------------------------------------
    def _post(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.endpoint.rstrip('/')}/{model}:{self.config.action}"
        status, body = self.transport(
            "POST",
            url,
            json.dumps(payload).encode(),
            {
                "Content-Type": "application/json",
                "x-goog-api-key": self.config.api_key,
            },
        )
        if status >= 400:
            raise ProviderUnavailableError(
                f"The paid image provider refused the request (HTTP {status}).",
                technical_detail=body[:400].decode("utf-8", "replace"),
                remediation="Check the configured key, endpoint and model tier.",
                blocked_reason=BlockedReason.MISSING_PROVIDER.value,
            )
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ProviderUnavailableError("The paid image provider returned no object.")
        return parsed

    def _request(self, parts: list[dict[str, Any]], seed: int) -> dict[str, Any]:
        """One request body, in the shape the REST API takes.

        ``responseModalities`` is what makes an image model return pixels rather
        than prose; the creator can override or extend any of it through
        ``CONTINUUM_GOOGLE_IMAGE_GENERATION_CONFIG`` without touching code.
        """
        generation: dict[str, Any] = {"responseModalities": ["IMAGE"]}
        if seed:
            generation["seed"] = int(seed)
        generation.update(self.config.generation_config)
        return {"contents": [{"role": "user", "parts": parts}], "generationConfig": generation}

    @staticmethod
    def _image(payload: dict[str, Any]) -> bytes:
        """The first inline image in the response, whatever wrapper it arrived in."""
        found = _first_inline_image(payload)
        if found is None:
            raise ProviderUnavailableError(
                "The paid image provider returned no image.",
                technical_detail=", ".join(sorted(payload)),
                remediation="Check the model tier: a text model cannot draw.",
                blocked_reason=BlockedReason.MISSING_MODEL.value,
            )
        return base64.b64decode(found)

    def _attachments(self, references: Sequence[ArtworkReference]) -> list[dict[str, Any]]:
        """Reference images, refusing any verbatim source excerpt outright."""
        parts = []
        for reference in references[: self.config.max_reference_images]:
            if reference_data_class(reference.provenance or {}) is DataClass.SOURCE_EXCERPT:
                raise ProviderUnavailableError(
                    "A source excerpt was about to be sent to a paid third party.",
                    technical_detail=f"reference {reference.reference_id}",
                    remediation=(
                        "Continuum withholds source excerpts before they reach a remote "
                        "provider; this request was assembled without that step."
                    ),
                    blocked_reason=BlockedReason.MISSING_SOURCE_ASSET.value,
                )
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(reference.data).decode(),
                    },
                    "continuum": {
                        "reference_id": reference.reference_id,
                        "purpose": reference.purpose,
                        "character": reference.character,
                    },
                }
            )
        return parts

    def _provenance(
        self, model: str, tier: str, settings: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        return {
            "backend": "GOOGLE_IMAGE",
            "model": {
                "name": model,
                "version": tier,
                # A hosted model exposes no weights to hash; the request is what
                # is reproducible, so its hash stands in and says so.
                "sha256": hashlib.sha256(
                    json.dumps({"model": model, "settings": settings}, sort_keys=True).encode()
                ).hexdigest(),
                "license": self.config.license_note or "vendor terms",
                "source": self.config.model_source or self.config.endpoint,
                "hosted": True,
            },
            "workflow": _workflow_manifest(),
            "settings": settings,
            "seed": seed,
            "tier": tier,
        }

    # -- contracts ------------------------------------------------------------
    def generate_image(self, request: GenerationRequest) -> GenerationResult:
        tier = str(request.options.get("tier") or ImageTier.CHEAP)
        model = self.config.model_for(tier)
        response = self._post(model, self._request([{"text": request.prompt}], request.seed or 0))
        data = self._image(response)
        return GenerationResult(
            provider_id=GOOGLE_PROVIDER_ID,
            model_ref=model,
            version=WORKFLOW_VERSION,
            structured={"image_base64": base64.b64encode(data).decode(), "tier": tier},
            usage={"images": 1},
        )

    def render_character_sheet(self, request: CharacterSheetRequest) -> CharacterSheetResult:
        tier = str(request.settings.get("tier") or ImageTier.HIGH)
        model = self.config.model_for(tier)
        prompt = _sheet_prompt(request)
        parts: list[dict[str, Any]] = [{"text": prompt}]
        parts.extend(self._attachments(request.references))
        settings = {
            "sheet_kind": request.sheet_kind,
            "views": list(request.views),
            "width": request.width,
            "height": request.height,
            "prompt": prompt,
            "reference_images": len(parts) - 1,
            "action": self.config.action,
        }
        response = self._post(model, self._request(parts, request.seed))
        data = self._image(response)
        image = probe(data)
        return CharacterSheetResult(
            provider_id=GOOGLE_PROVIDER_ID,
            output=RenderOutput.ARTWORK_CANDIDATE,
            image=RenderedImage(data, image.mime, image.width, image.height),
            provenance=self._provenance(model, tier, settings, request.seed),
        )

    def render_stage(self, request: PanelStageRequest) -> PanelStageResult:
        tier = str(request.settings.get("tier") or ImageTier.CHEAP)
        model = self.config.model_for(tier)
        identity = [r for r in request.references if identity_evidence(r)]
        lane, scene, not_conditioned = scene_references(request)
        prompt = _stage_prompt(request)
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if request.upstream is not None:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(request.upstream).decode(),
                    },
                    "continuum": {"role": "UPSTREAM_STAGE", "stage": request.upstream_stage},
                }
            )
        parts.extend(self._attachments([*scene, *identity]))
        settings = {
            "stage": request.stage,
            "width": request.width,
            "height": request.height,
            "prompt": prompt,
            "upstream_held_by": "attached image" if request.upstream is not None else None,
            "lettering": "disabled; Continuum owns text after artwork",
        }
        response = self._post(model, self._request(parts, request.seed))
        data = self._image(response)
        image = probe(data)
        provenance = self._provenance(model, tier, settings, request.seed)
        provenance["conditioning"] = {
            "identity": {
                name: [r.reference_id for r in identity if r.character == name]
                for name in sorted({str(r.character) for r in identity})
            },
            "scene": (
                {
                    "purpose": lane.value,
                    "mechanism": "attached reference images, labelled by purpose",
                    "weight": None,
                    "references": [r.reference_id for r in scene],
                }
                if scene
                else None
            ),
        }
        provenance["references_transmitted"] = [r.reference_id for r in [*scene, *identity]]
        provenance["references_not_conditioned"] = not_conditioned
        provenance["references_withheld"] = []
        return PanelStageResult(
            backend=ArtworkBackendKind.TEST,
            provider_id=GOOGLE_PROVIDER_ID,
            output=RenderOutput.ARTWORK_CANDIDATE,
            image=RenderedImage(data, image.mime, image.width, image.height),
            provenance=provenance,
        )


def _workflow_manifest() -> dict[str, str]:
    template = {"id": WORKFLOW_ID, "shape": "text+images -> one image", "letters": False}
    return {
        "id": WORKFLOW_ID,
        "version": WORKFLOW_VERSION,
        "sha256": hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest(),
    }


def _first_inline_image(payload: Any) -> str | None:
    """Find the first base64 image anywhere in the response, without a schema."""
    if isinstance(payload, dict):
        data = payload.get("data")
        mime = str(payload.get("mime_type") or payload.get("mimeType") or "")
        if isinstance(data, str) and mime.startswith("image/"):
            return data
        for value in payload.values():
            found = _first_inline_image(value)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _first_inline_image(value)
            if found is not None:
                return found
    return None


def _sheet_prompt(request: CharacterSheetRequest) -> str:
    lines = [
        f"A {request.sheet_kind.lower().replace('_', ' ')} model sheet, "
        f"{', '.join(v.lower().replace('_', ' ') for v in request.views)}, "
        "on a plain background, no text and no labels.",
        "Black and white manga drawing. Keep every attached reference's identity exactly.",
    ]
    lines.extend(f"Must hold: {rule}" for rule in request.identity_rules)
    lines.extend(f"Never: {rule}" for rule in request.restrictions)
    return "\n".join(lines)[:4000]


def _stage_prompt(request: PanelStageRequest) -> str:
    contract = request.contract
    stage = request.stage.lower().replace("_", " ")
    editable = ", ".join(request.stage_contract.get("editable") or [])
    frozen = ", ".join(request.stage_contract.get("frozen_before") or [])
    lines = [
        f"Black and white manga panel, {stage} stage.",
        f"Beat: {contract.get('beat') or ''}",
        f"Shot: {str(contract.get('shot') or '').lower()}",
        f"This stage may change: {editable}." if editable else "",
        f"Keep exactly as given: {frozen}." if frozen else "",
        *(f"Must show: {item}" for item in (contract.get("required") or [])[:4]),
        *(f"Never: {item}" for item in (contract.get("forbidden") or [])[:6]),
        *(f"Size lock: {lock}" for lock in (request.settings.get("scale_locks") or [])[:3]),
        str(request.settings.get("creator_notes") or ""),
    ]
    return "\n".join(line for line in lines if line)[:4000]


def google_image_config(settings: Any) -> GoogleImageConfig:
    """The configured paid provider, whether or not it is usable yet.

    Endpoint, method, model tiers and licence all have defaults, so the only
    thing the creator supplies is the key. ``missing()`` names what is absent.
    """
    key: Any = getattr(settings, "google_api_key", None)
    secret = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key or "")
    raw = str(getattr(settings, "google_image_generation_config", "") or "").strip()
    generation = json.loads(raw) if raw else {}
    if not isinstance(generation, dict):
        raise ValueError(
            "CONTINUUM_GOOGLE_IMAGE_GENERATION_CONFIG must be a JSON object, or empty."
        )
    return GoogleImageConfig(
        endpoint=str(getattr(settings, "google_image_endpoint", "") or ""),
        api_key=secret,
        models={
            ImageTier.CHEAP: str(getattr(settings, "google_image_model_cheap", "") or ""),
            ImageTier.HIGH: str(getattr(settings, "google_image_model_high", "") or ""),
        },
        action=str(getattr(settings, "google_image_action", "generateContent") or ""),
        generation_config=generation,
        license_note=str(getattr(settings, "google_image_license", "") or ""),
        model_source=str(getattr(settings, "google_image_source", "") or ""),
        timeout_seconds=float(getattr(settings, "google_image_timeout_seconds", 120.0)),
    )


def configured_google_provider(settings: Any) -> GoogleImageProvider | None:
    """The paid image provider, or None when the creator has not configured one.

    The enable flag is a three-state override: unset means "on when a key is
    present", and an explicit false means never. Registering the provider does
    not permit spending - the spend policy and the budget ledger decide that,
    separately and afterwards.
    """
    enabled = getattr(settings, "google_images_enabled", None)
    if enabled is False:
        return None
    config = google_image_config(settings)
    return GoogleImageProvider(config) if config.configured else None
