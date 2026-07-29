"""Builds and matches evidence pointers like ``crawl:<template>/<path>`` (spec §9).

The crawler does not put pointers in ``crawl.json`` — the triager builds them
from the distilled tree. This module holds the build rules and the matcher that
resolves a pointer back to a node.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

Node = dict[str, Any]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHOPIFY_SECTION_RE = re.compile(r"^shopify-section-(?:template--\d+__)?(.+)$")

# Attributes that make a good qualifier, most distinctive first.
_QUALIFIER_ATTRS = (
    "data-testid", "name", "aria-label", "data-section-type", "data-block-type",
    "type", "id", "href", "src", "placeholder", "title", "alt",
)

_LANDMARK_TAGS = frozenset({"header", "nav", "main", "footer", "aside", "form", "section"})


def slug(text: str, max_words: int = 4) -> str:
    """Turn text into a kebab-case slug of at most 4 words."""
    words = _SLUG_RE.sub(" ", (text or "").lower()).split()
    return "-".join(words[:max_words])


def _named(node: Node) -> tuple[str, str]:
    """Pick a node's name and where it came from: id, role, section, or tag."""
    attrs: dict[str, str] = node.get("attrs") or {}

    node_id = attrs.get("id")
    if node_id:
        section = _SHOPIFY_SECTION_RE.match(node_id)
        if section:
            return (slug(section.group(1)) or slug(node_id)), "id"
        return (slug(node_id) or node.get("tag", "")), "id"

    role = attrs.get("role")
    if role:
        return slug(role), "role"

    for key in ("data-section-type", "data-section", "data-block-type", "data-block"):
        if attrs.get(key):
            return slug(attrs[key]), "section"

    return node.get("tag", ""), "tag"


def segment_name(node: Node) -> str:
    """The name part of a path segment."""
    return _named(node)[0]


def segment_qualifier(node: Node, siblings: list[Node] | None = None, index: int | None = None) -> str | None:
    """The `[qualifier]` that tells a node apart from its siblings, if it needs one.

    Tries a distinctive attribute, then a text slug, then the sibling index.
    Names taken from an `id` are already unique, so they get no qualifier.
    """
    attrs: dict[str, str] = node.get("attrs") or {}
    name, source = _named(node)
    if source == "id":
        return None

    for key in _QUALIFIER_ATTRS:
        value = attrs.get(key)
        if not value:
            continue
        if key in ("href", "src"):
            value = value.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
        candidate = slug(value)
        if candidate and candidate != name:
            return candidate

    text = slug(node.get("text") or "")
    if text:
        return text

    if siblings is not None and index is not None:
        # Compare by identity: identical siblings are the reason this branch
        # exists, and `list.index` would return the first one for both.
        same = [s for s in siblings if segment_name(s) == name]
        position = _index_of(same, node)
        if len(same) > 1 and position is not None:
            return str(position + 1)
    return None


def _index_of(seq: list[Node], item: Node) -> int | None:
    """Position of `item` in `seq`, compared by identity."""
    for i, candidate in enumerate(seq):
        if candidate is item:
            return i
    return None


def segment(node: Node, siblings: list[Node] | None = None, index: int | None = None) -> str:
    """One path segment: the node's name plus its qualifier if it has one."""
    name = segment_name(node)
    qualifier = segment_qualifier(node, siblings, index)
    return f"{name}[{qualifier}]" if qualifier else name


def is_anchor(node: Node) -> bool:
    """True for landmarks and named sections, where a short path starts."""
    tag = node.get("tag", "")
    attrs: dict[str, str] = node.get("attrs") or {}
    if tag in _LANDMARK_TAGS:
        return True
    if attrs.get("role"):
        return True
    if any(attrs.get(k) for k in ("data-section-type", "data-section", "id")):
        return bool(attrs.get("id", "").startswith("shopify-section-")) or bool(
            attrs.get("data-section-type") or attrs.get("data-section")
        )
    return False


def build(template: str, ancestry: list[Node]) -> str:
    """Build a ``crawl:<template>/<path>`` pointer from a root-to-node chain.

    Paths start at the nearest landmark or named section, not the document root.
    """
    if not ancestry:
        return f"crawl:{template}"

    start = 0
    for i, node in enumerate(ancestry[:-1]):
        if is_anchor(node):
            start = i
    trail = ancestry[start:]

    segments: list[str] = []
    for i, node in enumerate(trail):
        parent = trail[i - 1] if i else None
        siblings = (parent.get("children") if parent else None) or None
        idx = _index_of(siblings, node) if siblings else None
        segments.append(segment(node, siblings, idx))
    return f"crawl:{template}/" + "/".join(segments)


def iter_paths(template: str, root: Node) -> Iterator[tuple[str, Node]]:
    """Yield every (pointer, node) pair in a distilled tree."""
    def walk(node: Node, ancestry: list[Node]) -> Iterator[tuple[str, Node]]:
        if node is None:
            return
        if "repeat" in node:
            sample = node["repeat"].get("sample")
            if sample:
                yield from walk(sample, ancestry)
            return
        chain = ancestry + [node]
        yield build(template, chain), node
        for child in node.get("children") or []:
            yield from walk(child, chain)

    yield from walk(root, [])


# --- normalized matching (spec §9) -----------------------------------------

_INDEX_QUALIFIER_RE = re.compile(r"\[(\d+)\]")


def normalize(pointer: str, drop_index: bool = True) -> str:
    """Lower-case a pointer, strip trailing slashes, and optionally drop [1]-style indexes."""
    p = (pointer or "").strip().lower().rstrip("/")
    if drop_index:
        p = _INDEX_QUALIFIER_RE.sub("", p)
    return p


def _split(pointer: str) -> tuple[str, list[str]]:
    """Split a pointer into its template name and path segments."""
    body = pointer.split(":", 1)[1] if ":" in pointer else pointer
    parts = [p for p in body.split("/") if p]
    return (parts[0] if parts else ""), parts[1:]


def matches(candidate: str, target: str) -> bool:
    """True if two pointers name the same node.

    Ignores case and index qualifiers, and accepts a suffix match so pointers
    that start at different anchors still line up.
    """
    a, b = normalize(candidate), normalize(target)
    if a == b:
        return True

    ns_a = candidate.split(":", 1)[0].lower() if ":" in candidate else ""
    ns_b = target.split(":", 1)[0].lower() if ":" in target else ""
    if ns_a and ns_b and ns_a != ns_b:
        return False

    tpl_a, segs_a = _split(a)
    tpl_b, segs_b = _split(b)
    if ns_a == "crawl" and tpl_a != tpl_b:
        return False
    if not segs_a or not segs_b:
        return False

    short, long = (segs_a, segs_b) if len(segs_a) <= len(segs_b) else (segs_b, segs_a)
    return long[-len(short):] == short


def resolve(pointer: str, crawl: dict[str, Any]) -> Node | None:
    """Find the node a ``crawl:`` pointer names, or None if it doesn't resolve."""
    if not pointer.lower().startswith("crawl:"):
        return None
    template = _split(normalize(pointer))[0]
    entry = (crawl.get("templates") or {}).get(template)
    if not entry or not entry.get("distilled"):
        return None
    for candidate, node in iter_paths(template, entry["distilled"]):
        if matches(candidate, pointer):
            return node
    return None
