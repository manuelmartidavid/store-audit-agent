"""Evidence pointer grammar — spec §9.

    crawl:<template>/<semantic-path>

    <semantic-path> ::= <segment> ( "/" <segment> )*
    <segment>       ::= <name> ( "[" <qualifier> "]" )?

The crawler does not emit pointers into ``crawl.json`` — the triager constructs
them from the distilled tree it is reading. What lives here is the other half of
the contract: construction rules the crawler can self-check against, and the
normalized matcher the harness uses to resolve a pointer back to a node.

Matching is normalized, not exact (spec §9). A correct finding with a near-miss
pointer is a matcher bug, not a model miss.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

Node = dict[str, Any]

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SHOPIFY_SECTION_RE = re.compile(r"^shopify-section-(?:template--\d+__)?(.+)$")

# Attributes that make a good qualifier, in preference order. Distinctive value
# first, because a name a model can read off the page is one it can reproduce.
_QUALIFIER_ATTRS = (
    "data-testid", "name", "aria-label", "data-section-type", "data-block-type",
    "type", "id", "href", "src", "placeholder", "title", "alt",
)

_LANDMARK_TAGS = frozenset({"header", "nav", "main", "footer", "aside", "form", "section"})


def slug(text: str, max_words: int = 4) -> str:
    """kebab-case, ≤4 words — the text-slug form of a qualifier."""
    words = _SLUG_RE.sub(" ", (text or "").lower()).split()
    return "-".join(words[:max_words])


def _named(node: Node) -> tuple[str, str]:
    """(name, source) per §9: id · role · Shopify section/block name · tag."""
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
    """`<name>` per §9: id · role · Shopify section/block name · tag."""
    return _named(node)[0]


def segment_qualifier(node: Node, siblings: list[Node] | None = None, index: int | None = None) -> str | None:
    """`[<qualifier>]` per §9 — a distinctive attr, a text slug, then index.

    A qualifier *disambiguates siblings*. An `id`-derived name is already unique
    in the document, so it takes none — qualifying it would produce two spellings
    of the same node and hand the model a second way to be almost right.
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
        # Identity, not equality: two structurally identical siblings are exactly
        # the case this branch exists for, and `list.index` would call them both
        # the first one.
        same = [s for s in siblings if segment_name(s) == name]
        position = _index_of(same, node)
        if len(same) > 1 and position is not None:
            return str(position + 1)
    return None


def _index_of(seq: list[Node], item: Node) -> int | None:
    for i, candidate in enumerate(seq):
        if candidate is item:
            return i
    return None


def segment(node: Node, siblings: list[Node] | None = None, index: int | None = None) -> str:
    name = segment_name(node)
    qualifier = segment_qualifier(node, siblings, index)
    return f"{name}[{qualifier}]" if qualifier else name


def is_anchor(node: Node) -> bool:
    """Landmarks and named sections — where a shallow path starts (§9)."""
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
    """Build ``crawl:<template>/<path>`` from a root-to-node ancestry.

    Paths are shallow by intent: anchored at the nearest landmark or named
    section, not the document root.
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
    """Every (pointer, node) pair in a distilled tree.

    The harness uses this to answer automatic-fail #2 — does this pointer resolve
    to something that is actually in the fixtures?
    """
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
    """Lower-case, strip trailing slashes, optionally drop index qualifiers."""
    p = (pointer or "").strip().lower().rstrip("/")
    if drop_index:
        p = _INDEX_QUALIFIER_RE.sub("", p)
    return p


def _split(pointer: str) -> tuple[str, list[str]]:
    body = pointer.split(":", 1)[1] if ":" in pointer else pointer
    parts = [p for p in body.split("/") if p]
    return (parts[0] if parts else ""), parts[1:]


def matches(candidate: str, target: str) -> bool:
    """Resolve case-insensitively, index-insensitively, and on suffix.

    Suffix matching is what absorbs anchor disagreement: the model anchored at
    ``product-form`` and the label at ``main/product-form`` describe the same
    node, and failing that run would be a matcher bug.
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
    """Find the node a ``crawl:`` pointer names, or None if it does not resolve."""
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
