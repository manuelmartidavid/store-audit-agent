"""Shrinks a raw DOM tree down to what the triager needs to read (spec §5).

Plain functions over the tree from ``js/dom_walk.js`` — no browser, no I/O, no
randomness, so the same input always distills to the same bytes.

Three steps, in order:

1. ``collapse_runs`` — a run of identical siblings keeps its first 5 and the
   rest become a repeat marker. Runs first, because the keep filter would
   otherwise remove the wrappers that form the run.
2. ``keep`` — an element stays if it matches a keep rule or has 2+ surviving
   children. Plain wrapper chains collapse into their content.
3. ``build_node`` — filter attributes, pick the text, carry image dimensions.

Invariant: when in doubt, keep. The triager can only cite what survives this
step.
"""

from __future__ import annotations

from typing import Any, Iterable

from .config import MAX_SIBLING_RUN, TEXT_KEEP_MIN_CHARS

Raw = dict[str, Any]
Node = dict[str, Any]

# --- keep vocabulary (spec §5) ---------------------------------------------

STRUCTURAL_TAGS = frozenset({"html", "head", "body"})
HEAD_TAGS = frozenset({"title", "meta", "link", "base"})
LANDMARK_TAGS = frozenset({"header", "nav", "main", "footer", "aside"})
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
INTERACTIVE_TAGS = frozenset(
    {"a", "button", "input", "select", "textarea", "form", "label", "option",
     "optgroup", "fieldset", "legend", "details", "summary", "dialog"}
)
MEDIA_TAGS = frozenset(
    {"img", "source", "video", "iframe", "picture", "audio", "track", "object", "embed"}
)
MICRODATA_ATTRS = frozenset({"itemscope", "itemtype", "itemprop", "itemid"})

# Elements whose text is a label or an accessible name. Their text is kept at any
# length; everything else needs 20+ characters.
NAME_CARRYING_TAGS = INTERACTIVE_TAGS | HEADING_TAGS | LANDMARK_TAGS | HEAD_TAGS

# Attributes that make any element interactive. Deliberately wide.
_CLICK_EVENTS = frozenset(
    {"click", "keydown", "keyup", "keypress", "mousedown", "mouseup", "submit",
     "change", "input", "focus", "blur", "touchstart", "touchend", "pointerdown",
     "pointerup", "toggle"}
)
_CLICK_ATTR_PREFIXES = ("@", "v-on:", "x-on:", "wire:", "hx-on", "ng-click", "data-action")
_CLICK_ATTR_NAMES = frozenset({"tabindex", "role", "data-action", "data-click", "ng-click"})

# A div dressed as a button is usually wired up by external JS, so it has no
# inline handler — just a data-* hook and/or a button-ish class.
# Invariant: keep both signals wide. axe can't see a JS-wired div-button
# either, so if distillation drops it nothing downstream can find it.
_DATA_HOOK_KEYWORDS = (
    "add", "cart", "toggle", "action", "click", "submit", "open", "close",
    "dismiss", "trigger", "tab", "modal", "dropdown", "menu", "accordion",
    "slide", "carousel", "remove", "buy", "checkout", "qty", "quantity",
    "expand", "collapse", "select", "increment", "decrement",
)
_CONTROL_CLASS_SUBSTRINGS = ("btn", "button", "cta")


def _has_control_class(attrs: dict) -> bool:
    """True when an element has a button-like class, even with no other signal."""
    classes = (attrs.get("class") or "").lower()
    return any(sub in classes for sub in _CONTROL_CLASS_SUBSTRINGS)

# For script and link we keep the reference and loading attributes, never bodies.
_SCRIPT_ATTRS = ("id", "src", "type", "async", "defer", "nomodule", "crossorigin", "integrity")
_LINK_ATTRS = (
    "id", "rel", "href", "type", "as", "media", "sizes", "hreflang", "crossorigin", "title",
)

# These never collapse: a head full of <meta> is not a repeated grid, and
# collapsing it would throw away evidence.
_NEVER_COLLAPSE = frozenset({"html", "head", "body", "title", "meta", "link", "script", "style", "base"})


def is_click_attr(name: str) -> bool:
    """True for attributes that wire behaviour onto an element."""
    lowered = name.lower()
    if lowered in _CLICK_ATTR_NAMES:
        return True
    if lowered.startswith("on") and lowered[2:] in _CLICK_EVENTS:
        return True
    if any(lowered.startswith(p) for p in _CLICK_ATTR_PREFIXES):
        return True
    if lowered.startswith("data-") and any(k in lowered for k in _DATA_HOOK_KEYWORDS):
        return True
    return False


def keep(raw: Raw) -> bool:
    """True if this element is worth keeping on its own merits (spec §5)."""
    tag = raw.get("tag", "")
    attrs: dict[str, str] = raw.get("attrs") or {}

    if tag in STRUCTURAL_TAGS or tag in HEAD_TAGS or tag in LANDMARK_TAGS:
        return True
    if tag in HEADING_TAGS or tag in INTERACTIVE_TAGS or tag in MEDIA_TAGS:
        return True
    if tag == "svg":  # keep the element and its aria attrs, drop the internals
        return True
    if tag == "script":
        return bool(attrs.get("src")) or bool(raw.get("text"))
    if tag == "style":
        return False
    if any(a in attrs for a in MICRODATA_ATTRS):
        return True
    if any(is_click_attr(name) for name in attrs):
        return True
    if _has_control_class(attrs):
        return True
    # Invariant: this prose rule is how page copy reaches the triager. Removing
    # it makes every copy-based finding impossible to detect.
    if len(raw.get("text") or "") > TEXT_KEEP_MIN_CHARS:
        return True
    return False


# --- repeat collapse (spec §5) ---------------------------------------------

def _run_key(raw: Raw) -> tuple[str, tuple[str, ...]]:
    """The tag+class key that decides whether two siblings are the same shape."""
    attrs: dict[str, str] = raw.get("attrs") or {}
    classes = tuple(sorted((attrs.get("class") or "").split()))
    return raw.get("tag", ""), classes


def collapse_runs(children: list[Raw]) -> list[Raw]:
    """Keep the first 5 of a run of identical siblings, then a repeat marker.

    Runs longer than 5 are collapsed. The marker carries the full run length
    and the 6th element as a sample, so it shows what the hidden items look
    like rather than repeating one already present.
    """
    out: list[Raw] = []
    i = 0
    n = len(children)
    while i < n:
        key = _run_key(children[i])
        j = i + 1
        while j < n and _run_key(children[j]) == key:
            j += 1
        run = children[i:j]
        if len(run) > MAX_SIBLING_RUN and key[0] not in _NEVER_COLLAPSE:
            out.extend(run[:MAX_SIBLING_RUN])
            out.append({"__repeat__": {"count": len(run), "sample": run[MAX_SIBLING_RUN]}})
        else:
            out.extend(run)
        i = j
    return out


# --- node construction ------------------------------------------------------

def _filter_attrs(tag: str, attrs: dict[str, str]) -> dict[str, str]:
    """Keep the attributes worth emitting for this tag, sorted by name."""
    if tag == "script":
        picked = {k: attrs[k] for k in _SCRIPT_ATTRS if k in attrs}
    elif tag == "link":
        picked = {k: attrs[k] for k in _LINK_ATTRS if k in attrs}
    else:
        picked = dict(attrs)
    return {k: picked[k] for k in sorted(picked)}


def _text_for(raw: Raw) -> str | None:
    """The text to emit for an element, or None if it has none worth keeping."""
    tag = raw.get("tag", "")
    own = raw.get("text") or ""
    attrs: dict[str, str] = raw.get("attrs") or {}

    if tag == "script":
        return own or None  # JSON-LD verbatim, already length-capped by the walker

    # A button's label often sits in a child: <button><span>Add to cart</span>.
    # Prefer the element's own text, fall back to descendant text.
    interactive = (
        tag in NAME_CARRYING_TAGS
        or "role" in attrs
        or any(is_click_attr(name) for name in attrs)
        or _has_control_class(attrs)
    )
    if not own and interactive:
        full = raw.get("full_text") or ""
        if full:
            return full
    if not own:
        return None
    if len(own) > TEXT_KEEP_MIN_CHARS or interactive:
        return own
    # Short text is cheap to keep, and dropping it loses prices, badges, and
    # stock labels.
    return own


def build_node(raw: Raw, children: list[Node]) -> Node:
    """Build one distilled node from a raw element and its distilled children."""
    tag = raw.get("tag", "")
    node: Node = {"tag": tag, "attrs": _filter_attrs(tag, raw.get("attrs") or {})}
    text = _text_for(raw)
    if text:
        node["text"] = text
    if tag == "img" and raw.get("dims"):
        node["dims"] = raw["dims"]
    if children:
        node["children"] = children
    return node


# --- the walk ---------------------------------------------------------------

def _distill_many(children: list[Raw]) -> list[Node]:
    """Collapse repeated siblings, then distill each one."""
    out: list[Node] = []
    for child in collapse_runs(children):
        out.extend(_distill_one(child))
    return out


def _distill_one(raw: Raw) -> list[Node]:
    """Distill one element into zero or more nodes."""
    marker = raw.get("__repeat__")
    if marker is not None:
        sample = _distill_one(marker["sample"])
        return [{"repeat": {"count": marker["count"], "sample": sample[0] if sample else None}}]

    children = _distill_many(raw.get("children") or [])
    # Worth keeping on its own, or a container that groups things. The second
    # part keeps product cards intact while div > div > h1 collapses to the h1.
    if keep(raw) or len(children) >= 2:
        return [build_node(raw, children)]
    return children


def distill(raw_root: Raw) -> Node:
    """Distill a whole raw document tree. Same input always gives same output."""
    nodes = _distill_one(raw_root)
    if not nodes:
        return {"tag": raw_root.get("tag", "html"), "attrs": {}}
    if len(nodes) == 1:
        return nodes[0]
    return {"tag": raw_root.get("tag", "html"), "attrs": {}, "children": nodes}


def iter_nodes(node: Node) -> Iterable[Node]:
    """Depth-first walk over a distilled tree, descending into repeat samples."""
    stack = [node]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        if "repeat" in current:
            sample = current["repeat"].get("sample")
            if sample:
                stack.append(sample)
            continue
        yield current
        stack.extend(reversed(current.get("children") or []))
