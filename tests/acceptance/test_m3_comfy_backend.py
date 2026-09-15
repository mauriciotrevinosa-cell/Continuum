"""M3: the ComfyUI page backend, proven against a fake ComfyUI server.

No GPU and no real ComfyUI are needed: an in-process HTTP server speaks the
parts of the ComfyUI API the adapter uses (``/object_info``, ``/upload/image``,
``/prompt``, ``/history``, ``/view``) and records what it received.

Pinned: backends are registered only when configured; a probe reports
reachability, missing nodes and the checkpoint truthfully; identity
conditioning is claimed only with IP-Adapter nodes; a render returns a master
and two finishes of the same geometry with complete, reproducible provenance;
only the page's own references are uploaded; a remote backend refuses source
manga excerpts unless explicitly allowed; an unreachable server blocks with a
reason instead of pretending.
"""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Iterator
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest
from continuum_config import Settings
from continuum_core import ProviderUnavailableError
from continuum_core.references import RenderOutput
from continuum_providers import artwork_backends, build_default_registry
from continuum_providers.artwork import (
    ArtworkBackendKind,
    ArtworkReference,
    PageRenderRequest,
    capability_gaps,
    check_result,
)
from continuum_providers.comfy import (
    CORE_NODES,
    IDENTITY_NODES,
    ComfyConfig,
    ComfyModel,
    ComfyPageProvider,
)
from PIL import Image

CHECKPOINT = "demo-page-model.safetensors"
MODEL = ComfyModel(
    name=CHECKPOINT,
    version="1.0",
    sha256="a" * 64,
    license="test-license",
    source="https://example.invalid/demo-page-model",
)


def _png(width: int, height: int, shade: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (shade, shade, shade)).save(buffer, format="PNG")
    return buffer.getvalue()


class FakeComfy:
    def __init__(self, *, identity: bool = True, checkpoint: str = CHECKPOINT) -> None:
        self.identity = identity
        self.checkpoint = checkpoint
        self.uploads: list[str] = []
        self.prompts: list[dict[str, Any]] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return

            def _send(self, status: int, body: bytes, kind: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                if self.path == "/object_info":
                    nodes: dict[str, Any] = {name: {} for name in CORE_NODES}
                    if fake.identity:
                        nodes.update({name: {} for name in IDENTITY_NODES})
                    nodes["CheckpointLoaderSimple"] = {
                        "input": {"required": {"ckpt_name": [[fake.checkpoint, "other.ckpt"]]}}
                    }
                    self._send(200, json.dumps(nodes).encode())
                elif self.path.startswith("/history/"):
                    prompt_id = self.path.rsplit("/", 1)[1]
                    index = int(prompt_id.split("-")[1])
                    self._send(
                        200,
                        json.dumps(
                            {
                                prompt_id: {
                                    "status": {"status_str": "success"},
                                    "outputs": {
                                        "9": {
                                            "images": [
                                                {
                                                    "filename": f"out-{index}.png",
                                                    "subfolder": "",
                                                    "type": "output",
                                                }
                                            ]
                                        }
                                    },
                                }
                            }
                        ).encode(),
                    )
                elif self.path.startswith("/view"):
                    graph = fake.prompts[-1]
                    latent = next(
                        n
                        for n in graph.values()
                        if n["class_type"] in {"EmptyLatentImage", "LoadImage"}
                    )
                    size = (latent["inputs"].get("width", 300), latent["inputs"].get("height", 420))
                    self._send(200, _png(*size, 90 + 40 * len(fake.prompts)), "image/png")
                else:
                    self._send(404, b"{}")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                if self.path == "/upload/image":
                    name = body.split(b'filename="', 1)[1].split(b'"', 1)[0].decode()
                    fake.uploads.append(name)
                    self._send(200, json.dumps({"name": name}).encode())
                elif self.path == "/prompt":
                    fake.prompts.append(json.loads(body)["prompt"])
                    self._send(200, json.dumps({"prompt_id": f"p-{len(fake.prompts)}"}).encode())
                else:
                    self._send(404, b"{}")

        return Handler

    def __enter__(self) -> FakeComfy:
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def comfy() -> Iterator[FakeComfy]:
    with FakeComfy() as server:
        yield server


def _request(references: tuple[ArtworkReference, ...] = ()) -> PageRenderRequest:
    return PageRenderRequest(
        page_key="demo-c1-s001",
        width=300,
        height=420,
        seed=11,
        page={"characters": ["Aster Vale"], "directions": ["Aster Vale on the pier, in profile."]},
        plan={},
        continuity={"character_rules": {"Aster Vale": {"forbidden_accessories": ["glasses"]}}},
        references=references,
        settings={"workflow": "page.v1"},
    )


def _ref(role: str, name: str, **provenance: Any) -> ArtworkReference:
    return ArtworkReference(
        role=role,
        reference_id=name,
        data=_png(64, 64, 200),
        character="Aster Vale",
        provenance=provenance,
    )


def _provider(url: str, **changes: Any) -> ComfyPageProvider:
    config = ComfyConfig(
        backend=ArtworkBackendKind.COMFY_LOCAL,
        base_url=url,
        model=MODEL,
        poll_seconds=0.01,
        timeout_seconds=5,
    )
    return ComfyPageProvider(replace(config, **changes))


def test_backends_are_registered_only_when_configured(comfy: FakeComfy) -> None:
    bare = Settings(_env_file=None)
    registry = build_default_registry(settings=bare)
    ids = {d.id for d in registry.descriptors()}
    assert "comfy.local" not in ids and "comfy.remote" not in ids
    states = {b["kind"]: b for b in artwork_backends(registry, bare)}
    assert states["TEST"]["ready"] and states["TEST"]["output"] == "TEST_RENDER"
    assert (
        states["COMFY_LOCAL"]["configured"] is False
        and "not configured" in states["COMFY_LOCAL"]["reason"]
    )
    assert states["COMFY_REMOTE"]["configured"] is False

    configured = Settings(
        _env_file=None,
        comfy_local_url=comfy.url,
        comfy_remote_url="http://127.0.0.1:9/secret-tunnel-path",
        comfy_checkpoint=CHECKPOINT,
        comfy_checkpoint_version="1.0",
        comfy_checkpoint_sha256="a" * 64,
        comfy_checkpoint_license="test-license",
        comfy_checkpoint_source="https://example.invalid/demo-page-model",
    )
    registry = build_default_registry(settings=configured)
    states = {b["kind"]: b for b in artwork_backends(registry, configured)}
    local, remote = states["COMFY_LOCAL"], states["COMFY_REMOTE"]
    assert local["configured"] and local["reachable"] and local["ready"]
    assert local["checkpoint_available"] and local["identity_conditioning"]
    assert local["model_metadata_missing"] == [] and local["workflow"]["sha256"]
    assert remote["configured"] and not remote["reachable"] and not remote["ready"]
    assert "secret-tunnel-path" not in json.dumps(remote), "a tunnel URL's path is never shown"
    assert registry.get("comfy.remote").descriptor.privacy_class.value == "THIRD_PARTY"


def test_probe_reports_missing_nodes_and_checkpoint() -> None:
    with FakeComfy(identity=False, checkpoint="something-else.safetensors") as server:
        provider = _provider(server.url)
        status = provider.status(refresh=True)
        assert (
            status.reachable
            and not status.checkpoint_available
            and not status.identity_conditioning
        )
        caps = provider.capabilities
        assert not caps.available and "checkpoint" in caps.notes
        assert capability_gaps(caps, _request()) == [caps.notes]
        with pytest.raises(ProviderUnavailableError, match="checkpoint"):
            provider.render_page(_request())


def test_render_returns_reproducible_sibling_finishes(comfy: FakeComfy) -> None:
    provider = _provider(comfy.url)
    references = (
        _ref("CANON", "ref-face", authority="CREATOR_PRIMARY"),
        _ref("CONTINUITY", "page-1"),
        _ref("GRAMMAR", "grammar-1"),
    )
    request = _request(references)
    assert capability_gaps(provider.capabilities, request) == []
    result = provider.render_page(request)
    assert result.output is RenderOutput.ARTWORK_CANDIDATE
    assert check_result(result) == []
    assert (
        (result.bw.width, result.bw.height)
        == (result.master.width, result.master.height)
        == (300, 420)
    )
    assert (result.color.width, result.color.height) == (300, 420)
    provenance = result.provenance
    assert provenance["model"]["sha256"] == "a" * 64 and provenance["workflow"]["id"]
    assert provenance["identity_references_sent"] == ["ref-face", "page-1"]
    assert provenance["references_not_used_by_this_workflow"] == ["grammar-1"]
    assert (
        "glasses" in provenance["settings"]["negative"]
        and "HUD" in provenance["settings"]["negative"]
    )
    # Two identity images and the master were uploaded - nothing else.
    assert len(comfy.uploads) == 3 and comfy.uploads[-1].startswith("continuum-master-")
    master_graph, color_graph = comfy.prompts
    assert {n["class_type"] for n in master_graph.values()} >= {"IPAdapterAdvanced", "KSampler"}
    assert any(
        n["class_type"] == "LoadImage" and n["inputs"]["image"] == comfy.uploads[-1]
        for n in color_graph.values()
    )


def test_remote_refuses_source_excerpts_unless_allowed(comfy: FakeComfy) -> None:
    excerpt = (_ref("CANON", "source-page", authority="PRIMARY_SOURCE", kind="source_page"),)
    remote = _provider(comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE)
    with pytest.raises(ProviderUnavailableError, match="source manga excerpt"):
        remote.render_page(_request(excerpt))
    assert comfy.uploads == [], "nothing left the machine"
    allowed = _provider(
        comfy.url, backend=ArtworkBackendKind.COMFY_REMOTE, allow_source_excerpts=True
    )
    assert check_result(allowed.render_page(_request(excerpt))) == []


def test_missing_model_metadata_is_not_reproducible(comfy: FakeComfy) -> None:
    provider = _provider(comfy.url, model=ComfyModel(name=CHECKPOINT))
    result = provider.render_page(_request())
    problems = check_result(result)
    assert problems and "model.sha256" in problems[0] and "model.license" in problems[0]


def test_unreachable_server_blocks_with_a_reason() -> None:
    provider = _provider("http://127.0.0.1:9")
    caps = provider.capabilities
    assert not caps.available and "not reachable" in caps.notes
    with pytest.raises(ProviderUnavailableError, match="not reachable"):
        provider.render_page(_request())
