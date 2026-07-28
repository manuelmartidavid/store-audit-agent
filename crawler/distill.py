"""Distillation — spec §5.

Raw DOM is ~500KB per store, mostly script bodies and SVG paths no finding will
ever cite. The triager reasons over the output of this module, so distillation is
part of the prompt architecture and its rules are conservative: **when in doubt,
keep.**

Pure functions over the raw tree produced by ``js/dom_walk.js``. No browser, no
I/O, no clock, no randomness — the same raw tree distills to the same bytes every
time, which is acceptance test §10.6 and the reason fixtures are worth freezing.

Pipeline, in order:

1. ``collapse_runs``  — sibling runs of identical tag+class collapse after 5,
   applied to the *raw* tree. It has to happen before the keep filter: a
   collection grid's product cards are ``li.grid__item`` wrappers, and if the
   filter elides them first there is no run left to recognise.
2. ``keep`` / elide   — an element survives if it matches a §5 keep rule or if it
   is a branching container (≥2 surviving children). Linear wrapper chains
   collapse into their content; structure that actually groups things stays.
3. ``build_node``     — attribute filtering, text selection, dimension carry.
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

# Elements whose text is an accessible name or a label, not prose. Their text is
# emitted regardless of length; everything else needs the §5 20-char threshold.
NAME_CARRYING_TAGS = INTERACTIVE_TAGS | HEADING_TAGS | LANDMARK_TAGS | HEAD_TAGS

# Attributes that make an arbitrary element interactive. This clause is what
# catches C-01's div-button, so it errs wide.
_CLICK_EVENTS = frozenset(
    {"click", "keydown", "keyup", "keypress", "mousedown", "mouseup", "submit",
     "change", "input", "focus", "blur", "touchstart", "touchend", "pointerdown",
     "pointerup", "toggle"}
)
_CLICK_ATTR_PREFIXES = ("@", "v-on:", "x-on:", "wire:", "hx-on", "ng-click", "data-action")
_CLICK_ATTR_NAMES = frozenset({"tabindex", "role", "data-action", "data-click", "ng-click"})

# A div-button is usually wired by external JS (getElementById + addEventListener),
# so it carries NO inline handler — only a data-* hook and/or a button-ish class.
# Golden entry 02's C-01 (`<div class="btn ... add-btn" data-add-to-cart>`) is
# exactly this, and it was dropped until these two signals were added. A JS-wired
# div-button is invisible to axe too, so if distillation misses it the antipattern
# is undetectable by construction. This errs wide by design.
_DATA_HOOK_KEYWORDS = (
    "add", "cart", "toggle", "action", "click", "submit", "open", "close",
    "dismiss", "trigger", "tab", "modal", "dropdown", "menu", "accordion",
    "slide", "carousel", "remove", "buy", "checkout", "qty", "quantity",
    "expand", "collapse", "select", "increment", "decrement",
)
_CONTROL_CLASS_SUBSTRINGS = ("btn", "button", "cta")


def _has_control_class(attrs: dict) -> bool:
    """True when an element is *styled* as a control (button-like class).

    Catches a div/span dressed as a button even when it carries no interactive
    attribute at all — the model then judges whether it is a real, operable
    control or an inaccessible impostor (C-01)."""
    classes = (attrs.get("class") or "").lower()
    return any(sub in classes for sub in _CONTROL_CLASS_SUBSTRINGS)

# Reference-only carriers: src/href plus loading semantics, never bodies (§5).
_SCRIPT_ATTRS = ("id", "src", "type", "async", "defer", "nomodule", "crossorigin", "integrity")
_LINK_ATTRS = (
    "id", "rel", "href", "type", "as", "media", "sizes", "hreflang", "crossorigin", "title",
)

# Runs of these never collapse: a head full of <meta> is not a repeated grid, and
# collapsing it would destroy exactly the evidence C-02 and S-01 ride on.
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
    """Does this element match a §5 keep rule in its own right?"""
    tag = raw.get("tag", "")
    attrs: dict[str, str] = raw.get("attrs") or {}

    if tag in STRUCTURAL_TAGS or tag in HEAD_TAGS or tag in LANDMARK_TAGS:
        return True
    if tag in HEADING_TAGS or tag in INTERACTIVE_TAGS or tag in MEDIA_TAGS:
        return True
    if tag == "svg":  # element kept with its role/aria attrs; internals counted
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
    # Prose. V-01/V-02/V-03 and the X-01 injection ride in on this clause; drop
    # it and the model-only findings become undetectable by construction.
    if len(raw.get("text") or "") > TEXT_KEEP_MIN_CHARS:
        return True
    return False


# --- repeat collapse (spec §5) ---------------------------------------------

def _run_key(raw: Raw) -> tuple[str, tuple[str, ...]]:
    attrs: dict[str, str] = raw.get("attrs") or {}
    classes = tuple(sorted((attrs.get("class") or "").split()))
    return raw.get("tag", ""), classes


def collapse_runs(children: list[Raw]) -> list[Raw]:
    """Collapse consecutive siblings of identical tag+class after 5 instances.

    Emits ``{"repeat": {"count": N, "sample": <raw>}}`` where ``count`` is the
    length of the whole run — the catalog-behaviour signal — and ``sample`` is
    the first collapsed element, so the marker shows what the 45 unseen cards
    look like rather than repeating one of the 5 already present.
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
    if tag == "script":
        picked = {k: attrs[k] for k in _SCRIPT_ATTRS if k in attrs}
    elif tag == "link":
        picked = {k: attrs[k] for k in _LINK_ATTRS if k in attrs}
    else:
        picked = dict(attrs)
    return {k: picked[k] for k in sorted(picked)}


def _text_for(raw: Raw) -> str | None:
    tag = raw.get("tag", "")
    own = raw.get("text") or ""
    attrs: dict[str, str] = raw.get("attrs") or {}

    if tag == "script":
        return own or None  # JSON-LD verbatim, already clamped by the walker

    # An accessible name commonly lives in a child element: <button><span>Add to
    # cart</span></button>. Own text is preferred; descendant text is the
    # fallback, and only for elements where a name can legitimately live.
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
    # Short prose on an element kept for structural reasons: cheap, and dropping
    # it loses price strings, badges and stock labels. Keep.
    return own


def build_node(raw: Raw, children: list[Node]) -> Node:
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
    out: list[Node] = []
    for child in collapse_runs(children):
        out.extend(_distill_one(child))
    return out


def _distill_one(raw: Raw) -> list[Node]:
    marker = raw.get("__repeat__")
    if marker is not None:
        sample = _distill_one(marker["sample"])
        return [{"repeat": {"count": marker["count"], "sample": sample[0] if sample else None}}]

    children = _distill_many(raw.get("children") or [])
    # Kept in its own right, or a branching container worth preserving. The
    # second clause is what keeps product cards intact while linear wrapper
    # chains (div > div > div > h1) collapse to the h1.
    if keep(raw) or len(children) >= 2:
        return [build_node(raw, children)]
    return children


def distill(raw_root: Raw) -> Node:
    """Distill a raw document tree into the §5 node structure.

    Deterministic: same input, same output, byte for byte.
    """
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
