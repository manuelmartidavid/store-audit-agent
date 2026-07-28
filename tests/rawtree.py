"""Build raw trees from HTML, matching what ``js/dom_walk.js`` emits.

A test double for the browser side. The contract between the walker and the
distiller is the raw tree, so this lets every §5 rule be exercised on a bare
interpreter; the live acceptance tests (§10) are what confirm the real walker
produces the same shape.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from crawler.config import MAX_DATA_URI_BYTES

VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
     "param", "source", "track", "wbr"}
)
NAME_CARRIERS = frozenset(
    {"a", "button", "label", "summary", "option", "legend", "th", "td",
     "h1", "h2", "h3", "h4", "h5", "h6"}
)

_WS = re.compile(r"\s+")


def _collapse(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


class _Builder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: dict[str, Any] | None = None
        self.stack: list[dict[str, Any]] = []
        self.comments = 0

    def _make(self, tag: str, attrs) -> dict[str, Any]:
        return {
            "tag": tag.lower(),
            "attrs": {k.lower(): (v if v is not None else "") for k, v in attrs},
            "children": [],
            "_own": [],
        }

    def _attach(self, node: dict[str, Any]) -> None:
        if self.stack:
            self.stack[-1]["children"].append(node)
        elif self.root is None:
            self.root = node

    def handle_starttag(self, tag, attrs):
        node = self._make(tag, attrs)
        self._attach(node)
        if tag.lower() not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._attach(self._make(tag, attrs))

    def handle_endtag(self, tag):
        tag = tag.lower()
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i]["tag"] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        if self.stack:
            self.stack[-1]["_own"].append(data)

    def handle_comment(self, data):
        self.comments += 1


def _truncate_data_uris(attrs: dict[str, str]) -> dict[str, str]:
    out = {}
    for key, value in attrs.items():
        if len(value) > MAX_DATA_URI_BYTES and value.lstrip().lower().startswith("data:"):
            comma = value.find(",")
            head = value[: comma + 1] if comma != -1 else "data:"
            value = f"{head}[dropped {len(value)} bytes]"
        out[key] = value
    return out


def _all_text(node: dict[str, Any]) -> str:
    parts = list(node.get("_own", []))
    for child in node["children"]:
        parts.append(_all_text(child))
    return " ".join(p for p in parts if p)


def _finalize(node: dict[str, Any], dropped: dict[str, int]) -> dict[str, Any]:
    tag = node["tag"]
    own = _collapse("".join(node.get("_own", [])))
    out: dict[str, Any] = {"tag": tag, "attrs": _truncate_data_uris(node["attrs"]), "children": []}

    if tag == "style":
        dropped["style_blocks"] += 1
        return out

    if tag == "script":
        if own.strip():
            dropped["script_bodies"] += 1
        if node["attrs"].get("type", "").lower() == "application/ld+json" and own.strip():
            out["text"] = "".join(node.get("_own", [])).strip()
        return out

    if own:
        out["text"] = own

    if tag in NAME_CARRIERS or "role" in node["attrs"] or "tabindex" in node["attrs"]:
        full = _collapse(_all_text(node))
        if full and full != own:
            out["full_text"] = full

    if tag == "svg":
        stack = list(node["children"])
        count = 0
        while stack:
            child = stack.pop()
            count += 1
            stack.extend(child["children"])
        dropped["svg_internals"] += count
        return out

    out["children"] = [_finalize(child, dropped) for child in node["children"]]
    return out


def build(html: str) -> tuple[dict[str, Any], dict[str, int]]:
    """Parse HTML into (raw_tree, dropped_counts)."""
    builder = _Builder()
    builder.feed(html)
    builder.close()
    root = builder.root or {"tag": "html", "attrs": {}, "children": [], "_own": []}
    dropped = {"script_bodies": 0, "style_blocks": 0, "svg_internals": 0, "comment_nodes": builder.comments}
    return _finalize(root, dropped), dropped
