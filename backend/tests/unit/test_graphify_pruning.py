"""The graph is pruned of what is not there any more.

The knowledge graph is a map of this repository, and a map that carries
the parts of a building that was pulled down is worse than no map: a
reader cannot tell which half is true. The rebuild keeps every node it
did not make afresh, so the pruning is what puts the map back in step
with the code.

The graph's tool is stood in for here, because the backend's
dependencies do not include it and because the test is about the rule
and not about how the tool hashes a file.
"""

import hashlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "docker-compose.prod.yml").is_file()
    ),
    None,
)

pytestmark = pytest.mark.skipif(
    REPO_ROOT is None, reason="the deployment files are not in this checkout"
)


def _load_the_script():
    """The relabel script, loaded by its path."""
    path = REPO_ROOT / "infra/scripts/graphify-relabel.py"
    spec = importlib.util.spec_from_file_location("graphify_relabel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stand_in_for_the_tool(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A tool whose hash is the hash of the bytes, and whose cache is empty.

    The real one hashes the contents and the path together, and reads
    markdown without its frontmatter. The rule under test is which nodes
    are taken out, and not how a file is hashed.
    """
    cache = tmp_path / "cache" / "semantic"
    cache.mkdir(parents=True)

    def file_hash(path: Path, root: Path = Path(".")) -> str:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def cache_dir(root: Path = Path("."), kind: str = "ast") -> Path:
        return cache

    module = types.ModuleType("graphify.cache")
    module.file_hash = file_hash
    module.cache_dir = cache_dir
    package = types.ModuleType("graphify")
    package.cache = module
    monkeypatch.setitem(sys.modules, "graphify", package)
    monkeypatch.setitem(sys.modules, "graphify.cache", module)


def _node(node_id: str, source: str, *, in_the_file: bool) -> dict:
    """A node the tool made, with a place in the file."""
    return {
        "id": node_id,
        "label": node_id,
        "source_file": source,
        "source_location": "L1" if in_the_file else None,
    }


def test_a_node_about_a_file_that_is_not_there_is_taken_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stand_in_for_the_tool(monkeypatch, tmp_path)
    script = _load_the_script()

    (tmp_path / "here.py").write_text("x = 1\n")
    data = {
        "nodes": [
            _node("here", "here.py", in_the_file=True),
            _node("gone", "gone.py", in_the_file=True),
        ],
        "links": [{"source": "here", "target": "gone"}],
        "hyperedges": [{"id": "h", "nodes": ["here", "gone"]}],
    }

    dropped, edges_dropped = script.prune_stale(data, tmp_path)

    assert dropped == 1
    assert edges_dropped == 1
    assert [n["id"] for n in data["nodes"]] == ["here"]
    assert data["links"] == []
    assert data["hyperedges"] == []


def test_the_provider_s_notes_about_a_file_that_has_changed_are_taken_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider read an older version of the file, and its notes are older too."""
    _stand_in_for_the_tool(monkeypatch, tmp_path)
    script = _load_the_script()

    (tmp_path / "changed.py").write_text("x = 1\n")
    data = {
        "nodes": [
            _node("changed_note", "changed.py", in_the_file=False),
            _node("changed_tool", "changed.py", in_the_file=True),
        ],
        "links": [],
        "hyperedges": [],
    }

    dropped, _ = script.prune_stale(data, tmp_path)

    # The tool's own node was made afresh, so it is about the file as it
    # is now, and it stays.
    assert dropped == 1
    assert [n["id"] for n in data["nodes"]] == ["changed_tool"]


def test_the_provider_s_notes_about_a_file_it_has_read_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stand_in_for_the_tool(monkeypatch, tmp_path)
    script = _load_the_script()

    (tmp_path / "same.py").write_text("x = 1\n")
    # The provider has read this file, and its notes are in the cache.
    digest = hashlib.sha256((tmp_path / "same.py").read_bytes()).hexdigest()
    (tmp_path / "cache" / "semantic" / f"{digest}.json").write_text("{}")

    data = {
        "nodes": [_node("same_note", "same.py", in_the_file=False)],
        "links": [],
        "hyperedges": [],
    }

    dropped, _ = script.prune_stale(data, tmp_path)

    assert dropped == 0
    assert [n["id"] for n in data["nodes"]] == ["same_note"]
