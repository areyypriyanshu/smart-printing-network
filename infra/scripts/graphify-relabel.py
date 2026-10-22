#!/usr/bin/env python3
"""Put the community names back on the knowledge graph after a rebuild.

`graphify update` re-runs the community detection every time, and the
community *numbers* it hands out depend on the order the nodes were added to
the graph. That order is not stable between runs, so a name written against
community 12 can end up on community 19 after the next rebuild, and the
report quietly starts lying about what each part of the system is.

So the names are stored against something that does not move: the id of the
most connected member of the community. This script re-attaches the names to
the communities that now hold those members, and regenerates the report and
the HTML view.

Usage:
    python3 infra/scripts/graphify-relabel.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

OUT = Path("graphify-out")
GRAPH = OUT / "graph.json"
LABELS = OUT / ".graphify_labels.json"  # community id -> name
KEYS = OUT / ".graphify_label_keys.json"  # stable member id -> name
OVERRIDES = OUT / ".graphify_label_overrides.json"  # community id -> name, hand edited
DETECT = OUT / ".graphify_detect.json"
COST = OUT / "cost.json"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def prune_stale(data: dict, root: Path) -> tuple[int, int]:
    """Take out the parts of the graph that are about files that are not there.

    The rebuild keeps every node it did not make afresh, so a file that
    has been deleted leaves its nodes behind, and a file that has been
    changed keeps the notes the provider wrote about the older version
    of it. The first is a map of a building that is no longer there, and
    the second is a map that disagrees with the code.

    So two kinds of node are taken out: every node whose file is gone,
    and the provider's own notes about a file that has changed since the
    provider read it. What is left says what is true.

    The provider's notes are the nodes with no place in the file, and a
    file it has read is one whose hash is in its cache.

    Returns how many nodes and edges were taken out.
    """
    from graphify.cache import cache_dir, file_hash

    cached = {p.stem for p in cache_dir(root, "semantic").glob("*.json")}
    nodes = data.get("nodes", [])
    kept: list[dict] = []
    dropped: set[str] = set()
    for node in nodes:
        source = node.get("source_file")
        if not source:
            kept.append(node)
            continue
        path = Path(root) / source
        if not path.is_file():
            dropped.add(node["id"])
            continue
        if node.get("source_location"):
            # The tool's own node. It was made afresh from the file, so
            # it is about the file as it is now.
            kept.append(node)
            continue
        try:
            digest = file_hash(path, root)
        except OSError:
            dropped.add(node["id"])
            continue
        if digest not in cached:
            # The provider read an older version of this file.
            dropped.add(node["id"])
            continue
        kept.append(node)

    links = data.get("links", data.get("edges", []))
    kept_links = [
        link
        for link in links
        if link.get("source") not in dropped and link.get("target") not in dropped
    ]

    hyperedges = data.get("hyperedges", [])
    kept_hyperedges = [
        edge for edge in hyperedges if not (set(edge.get("nodes", [])) & dropped)
    ]
    nested = data.get("graph", {}).get("hyperedges", [])
    if nested:
        data["graph"]["hyperedges"] = [
            edge for edge in nested if not (set(edge.get("nodes", [])) & dropped)
        ]

    data["nodes"] = kept
    data["links"] = kept_links
    data["hyperedges"] = kept_hyperedges
    data.pop("edges", None)
    return len(dropped), len(links) - len(kept_links)


def main() -> int:
    if not GRAPH.exists():
        print("graphify-out/graph.json is missing. Run `make graph` first.", file=sys.stderr)
        return 1

    import networkx as nx

    data = load_json(GRAPH, {})
    nodes = data.get("nodes", [])
    if not nodes:
        print("graphify-out/graph.json holds no nodes.", file=sys.stderr)
        return 1

    gone, edges_gone = prune_stale(data, Path(".").resolve())
    if gone:
        GRAPH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Took out {gone} node(s) about files that are not there any more.")
    nodes = data.get("nodes", [])
    links = data.get("links", data.get("edges", []))

    graph = nx.Graph()
    for node in nodes:
        attrs = {k: v for k, v in node.items() if k != "id"}
        graph.add_node(node["id"], **attrs)
    for link in links:
        attrs = {k: v for k, v in link.items() if k not in ("source", "target")}
        graph.add_edge(link["source"], link["target"], **attrs)

    communities: dict[int, list[str]] = {}
    for node in nodes:
        communities.setdefault(node.get("community", 0), []).append(node["id"])

    degree = dict(graph.degree())
    # The name of a community is remembered against one of its members, a
    # real symbol in the code. That member is what the name follows when the
    # community is renumbered by the next rebuild.
    keys = load_json(KEYS, {})
    if not keys:
        # First run: the names graphify wrote are the only ones we have, so
        # they become the names we remember.
        by_id = {int(cid): name for cid, name in load_json(LABELS, {}).items()}
        keys = {}
        for cid, members in communities.items():
            if cid in by_id:
                top = max(members, key=lambda m: (degree.get(m, 0), m))
                keys[top] = by_id[cid]

    labels: dict[int, str] = {}
    overrides = {int(cid): name for cid, name in load_json(OVERRIDES, {}).items()}
    for cid, members in communities.items():
        # A community keeps the name of any member it still holds, so a name
        # that moved to a differently numbered community comes back.
        known = [m for m in members if m in keys]
        if known:
            carrier = max(known, key=lambda m: (degree.get(m, 0), m))
            labels[cid] = keys[carrier]
        else:
            top = max(members, key=lambda m: (degree.get(m, 0), m))
            raw_label = str(graph.nodes[top].get("label", "")).strip()
            # A useful fallback is better than a number: the most connected
            # symbol is usually the subsystem's name (e.g. "PaymentGateway"
            # or "PRD Requirements"). Keep it short for report headings.
            fallback = " ".join(raw_label.replace("_", " ").split())[:48].strip(" -:/")
            labels[cid] = fallback or f"Community {cid}"
            keys[top] = labels[cid]
        if cid in overrides:
            labels[cid] = overrides[cid]
            carrier = max(known, key=lambda m: (degree.get(m, 0), m)) if known else max(
                members, key=lambda m: (degree.get(m, 0), m)
            )
            keys[carrier] = overrides[cid]

    LABELS.write_text(json.dumps({str(k): v for k, v in labels.items()}, indent=2))
    KEYS.write_text(json.dumps(keys, indent=2))

    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.cluster import score_all
    from graphify.export import to_html
    from graphify.report import generate

    detect = load_json(DETECT, {})
    cost = load_json(COST, {})
    runs = cost.get("runs") or [{}]
    tokens = {
        "input": runs[-1].get("input_tokens", 0),
        "output": runs[-1].get("output_tokens", 0),
    }

    cohesion = score_all(graph, communities)
    gods = god_nodes(graph)
    surprises = surprising_connections(graph, communities)
    questions = suggest_questions(graph, communities, labels)

    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detect,
        tokens,
        ".",
        suggested_questions=questions,
        built_at_commit=data.get("built_at_commit"),
    )
    (OUT / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    # The HTML view is a picture of the graph, and it is only drawn when
    # the graph is small enough for the picture to be worth drawing. The
    # tool that built the graph makes the same decision and says so when
    # it skips it, and the limit can be raised with
    # GRAPHIFY_VIZ_NODE_LIMIT. The graph and the report are the parts
    # that are read; the picture is a convenience.
    limit = int(os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT", "5000"))
    if len(nodes) > limit:
        print(
            f"the graph has {len(nodes)} nodes, which is more than the limit of "
            f"{limit} for the HTML view, so the view is not drawn. The graph and "
            "the report are written. Raise GRAPHIFY_VIZ_NODE_LIMIT to draw it."
        )
    else:
        to_html(graph, communities, str(OUT / "graph.html"), community_labels=labels or None)

    print(f"Labelled {len(labels)} communities; the report is regenerated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
