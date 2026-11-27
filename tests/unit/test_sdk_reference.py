"""Regression checks for generated SDK reference (Python 3.11+)."""

import ast
import importlib.util
import shutil
from pathlib import Path

import pytest

pytest.importorskip(
    "tomllib", reason="SDK documentation generator requires Python 3.11+"
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "generate_sdk_reference", ROOT / "scripts" / "generate_sdk_reference.py"
)
generator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator)


@pytest.fixture(scope="module")
def pages():
    return generator.build_pages(ROOT)


def test_reference_is_complete_and_ordered(pages):
    assert len(pages) == 16
    orders = [int(p.split("nav_order: ")[1].splitlines()[0]) for p in pages.values()]
    assert len(orders) == len(set(orders))
    assert all(generator.MARKER in p for p in pages.values())
    assert all("category: sdk-reference\n" in p for p in pages.values())
    index = pages["sdk-reference-client.md"]
    assert "title: Client configuration\n" in index
    assert "Signatures are extracted from source" not in index
    for filename in pages:
        if filename != "sdk-reference-client.md":
            assert f"(/docs/{Path(filename).stem})" in index
    for slug, _, namespace, _, _, approved in generator.CLIENTS:
        page = pages[f"sdk-reference-{slug}.md"]
        for method in approved.split():
            assert f"### `client.{namespace}.{method}()`" in page


def test_version_from_package_metadata(pages):
    version = generator.tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
        "version"
    ]
    assert all(f"SDK version: `{version}`" in p for p in pages.values())


def test_excludes_unapproved_methods(pages):
    joined = "\n".join(pages.values())
    for method in (
        "threads.create_user",
        "runs.delete_run",
        "runs.generate",
        "runs.chat",
        "runs.update_run_fields",
        "messages.update_message",
        "assistants.bootstrap_playground_assistant",
        "actions.create_action",
        "vectors.create_vector_store_for_user",
        "keys.create_key_for_user",
    ):
        assert f"### `client.{method}()`" not in joined


def test_native_byok_and_events(pages):
    assert (
        "provider_key_id: Optional[str] = None" in pages["sdk-reference-streaming.md"]
    )
    events = pages["sdk-reference-events.md"]
    for name in generator.EVENTS:
        assert f"### `{name}`" in events
    assert "run_id: str" in events
    assert (
        "Import: `projectdavid.events.ScratchpadEvent`" in events
        or "Import: `projectdavid.ScratchpadEvent`" in events
    )
    assert "def execute(tool_executor:" in events
    assert "_runs_client:" not in events
    assert "Serialization type: `tool_call_manifest`" in events


def test_response_models(pages):
    ledger = pages["sdk-reference-execution-accounting.md"]
    for name in generator.LEDGER_MODELS:
        assert f"### `{name}`" in ledger
    assert "Field(default_factory=list)" in ledger
    mcp = pages["sdk-reference-mcp.md"]
    assert "### `McpToolCollection`" in mcp
    assert "def select(*names: str)" in mcp


def test_signature_preserves_python_calling_conventions():
    node = ast.parse(
        "async def sample(self, a: int, /, b=1, *items: str, c, d: bool=True, **opts) -> None: pass"
    ).body[0]
    actual = generator.signature(node)
    assert "async def sample(" in actual
    assert (
        "a: int, /," in actual.replace("\n", "").replace("    ", "")
        or "    /,\n" in actual
    )
    assert "*items: str" in actual
    assert "d: bool = True" in actual
    assert "**opts" in actual
    assert actual.endswith("-> None")


def test_missing_approved_method_fails(tmp_path):
    root = tmp_path / "sdk"
    shutil.copytree(ROOT / "src", root / "src")
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    path = root / "src/projectdavid/clients/threads_client.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "def create_thread(", "def removed_create_thread("
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="create_thread"):
        generator.build_pages(root)


def test_new_method_not_published(tmp_path, pages):
    root = tmp_path / "sdk"
    shutil.copytree(ROOT / "src", root / "src")
    shutil.copyfile(ROOT / "pyproject.toml", root / "pyproject.toml")
    path = root / "src/projectdavid/clients/threads_client.py"
    text = path.read_text(encoding="utf-8").replace(
        "class ThreadsClient(BaseAPIClient):",
        "class ThreadsClient(BaseAPIClient):\n    def unapproved(self):\n        pass\n",
    )
    path.write_text(text, encoding="utf-8")
    assert generator.build_pages(root) == pages


def test_deterministic_and_check(tmp_path, pages):
    assert generator.build_pages(ROOT) == pages
    generator.publish(pages, tmp_path)
    generator.publish(pages, tmp_path, check=True)
    original = {p.name: p.read_bytes() for p in tmp_path.glob("*.md")}
    generator.publish(pages, tmp_path)
    assert original == {p.name: p.read_bytes() for p in tmp_path.glob("*.md")}
    path = tmp_path / next(iter(pages))
    path.write_text(path.read_text(encoding="utf-8") + "\nchanged", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        generator.publish(pages, tmp_path, check=True)


def test_protect_handwritten_and_remove_stale_generated(tmp_path, pages):
    handwritten = tmp_path / "manual.md"
    handwritten.write_text("Manual guide", encoding="utf-8")
    with pytest.raises(ValueError, match="handwritten"):
        generator.publish(pages, tmp_path)
    assert handwritten.read_text() == "Manual guide"
    assert len(list(tmp_path.iterdir())) == 1
    handwritten.unlink()
    stale = tmp_path / "old.md"
    stale.write_text(generator.MARKER, encoding="utf-8")
    generator.publish(pages, tmp_path)
    assert not stale.exists()
