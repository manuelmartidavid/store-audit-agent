"""Checks that a crawl.json has the shape everything downstream expects (spec §4, §6).

Every check returns a list of readable problems; an empty list means it's valid.
"""

from __future__ import annotations

from typing import Any

from . import SCHEMA_CRAWL
from .config import TEMPLATES

STATUSES = {"complete", "partial", "blocked"}
GATES = {"none", "password_supplied", "blocked"}
TEMPLATE_STATUSES = {"captured", "absent", "blocked_by_robots", "error", "blocked"}
BLOCK_KINDS = {"password_page", "bot_challenge", "http_error", "dns"}
PLATFORMS = {"shopify", "woocommerce", "custom", "unknown"}
DROPPED_KEYS = {"script_bodies", "style_blocks", "svg_internals", "comment_nodes"}


def validate_crawl(crawl: dict[str, Any]) -> list[str]:
    """Check a whole crawl.json and return everything wrong with it."""
    problems: list[str] = []
    add = problems.append

    if crawl.get("schema") != SCHEMA_CRAWL:
        add(f"schema must be {SCHEMA_CRAWL!r}, got {crawl.get('schema')!r}")
    if not crawl.get("origin"):
        add("origin is required")
    if crawl.get("status") not in STATUSES:
        add(f"status must be one of {sorted(STATUSES)}, got {crawl.get('status')!r}")
    if crawl.get("gate") not in GATES:
        add(f"gate must be one of {sorted(GATES)}, got {crawl.get('gate')!r}")

    problems += _validate_fingerprint(crawl.get("fingerprint"))
    problems += _validate_templates(crawl)

    status = crawl.get("status")
    templates = crawl.get("templates") or {}
    captured = [t for t, e in templates.items() if isinstance(e, dict) and e.get("status") == "captured"]
    errored = [t for t, e in templates.items() if isinstance(e, dict) and e.get("status") == "error"]

    if status == "blocked":
        if captured:
            add("status 'blocked' requires zero captured templates")
        problems += _validate_block(crawl.get("block"))
        fingerprint = crawl.get("fingerprint") or {}
        # A store we never got into has no fingerprint, no matter how
        # recognisable the page that blocked us looked (MNC-003).
        if fingerprint.get("platform") != "unknown":
            add("a blocked crawl must report platform 'unknown'")
        if fingerprint.get("evidence") or fingerprint.get("theme") or fingerprint.get("apps"):
            add("a blocked crawl must report an empty fingerprint")
    elif status == "partial":
        if not captured or not errored:
            add("status 'partial' means at least one template captured and at least one errored")
    elif status == "complete":
        if not captured:
            add("status 'complete' requires at least one captured template")
        if errored:
            add("status 'complete' cannot coexist with an errored template")

    return problems


def _validate_fingerprint(fingerprint: Any) -> list[str]:
    """Check the fingerprint block: platform, evidence, theme, and apps."""
    if not isinstance(fingerprint, dict):
        return ["fingerprint is required"]
    problems = []
    if fingerprint.get("platform") not in PLATFORMS:
        problems.append(f"fingerprint.platform must be one of {sorted(PLATFORMS)}")
    if not isinstance(fingerprint.get("evidence"), list):
        problems.append("fingerprint.evidence must be a list")
    theme = fingerprint.get("theme", "missing")
    if theme != "missing" and theme is not None and not isinstance(theme, dict):
        problems.append("fingerprint.theme must be an object or null")
    if not isinstance(fingerprint.get("apps"), list):
        problems.append("fingerprint.apps must be a list")
    else:
        for app in fingerprint["apps"]:
            if not isinstance(app, dict) or "name" not in app or "evidence" not in app:
                problems.append("each fingerprint.apps entry needs name and evidence")
                break
    return problems


def _validate_block(block: Any) -> list[str]:
    """Check the block object a blocked crawl must carry."""
    if not isinstance(block, dict):
        return ["a blocked crawl must carry a block object"]
    problems = []
    if block.get("kind") not in BLOCK_KINDS:
        problems.append(f"block.kind must be one of {sorted(BLOCK_KINDS)}")
    if not block.get("evidence"):
        problems.append("block.evidence is required")
    if "final_url" not in block:
        problems.append("block.final_url is required")
    return problems


def _validate_templates(crawl: dict[str, Any]) -> list[str]:
    """Check that all six template entries are present and well formed."""
    templates = crawl.get("templates")
    if not isinstance(templates, dict):
        return ["templates is required"]

    problems = []
    missing = [t for t in TEMPLATES if t not in templates]
    if missing:
        problems.append(f"templates is missing {missing} — all six keys are always present")
    extra = [t for t in templates if t not in TEMPLATES]
    if extra:
        problems.append(f"templates has unknown keys {extra}")

    for name in TEMPLATES:
        entry = templates.get(name)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            problems.append(f"templates.{name} must be an object")
            continue
        for key in ("url", "status", "http_status", "distilled", "dropped"):
            if key not in entry:
                problems.append(f"templates.{name} is missing {key!r}")
        if entry.get("status") not in TEMPLATE_STATUSES:
            problems.append(f"templates.{name}.status must be one of {sorted(TEMPLATE_STATUSES)}")
        if entry.get("status") == "captured":
            if not isinstance(entry.get("distilled"), dict):
                problems.append(f"templates.{name} is captured but has no distilled tree")
            dropped = entry.get("dropped")
            if not isinstance(dropped, dict) or set(dropped) != DROPPED_KEYS:
                problems.append(f"templates.{name}.dropped must carry exactly {sorted(DROPPED_KEYS)}")
            if not entry.get("url"):
                problems.append(f"templates.{name} is captured but has no url")
        problems += _validate_node(entry.get("distilled"), f"templates.{name}.distilled")
    return problems


def _validate_node(node: Any, path: str, depth: int = 0) -> list[str]:
    """Check one distilled node and everything under it."""
    if node is None or depth > 200:
        return []
    if not isinstance(node, dict):
        return [f"{path} must be an object"]
    if "repeat" in node:
        marker = node["repeat"]
        if not isinstance(marker, dict) or not isinstance(marker.get("count"), int):
            return [f"{path}.repeat needs an integer count"]
        return _validate_node(marker.get("sample"), f"{path}.repeat.sample", depth + 1)

    problems = []
    if "tag" not in node:
        problems.append(f"{path} is missing 'tag'")
    if not isinstance(node.get("attrs"), dict):
        problems.append(f"{path}.attrs must be an object")
    if "text" in node and not isinstance(node["text"], str):
        problems.append(f"{path}.text must be a string")
    for i, child in enumerate(node.get("children") or []):
        problems += _validate_node(child, f"{path}.children[{i}]", depth + 1)
    return problems
