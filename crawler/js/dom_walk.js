// Copies the live DOM into a JSON-safe tree, plus counts of the four things it
// never carries: script bodies, style blocks, svg internals, and comments.
//
// Returns: { raw: <node>, dropped: {script_bodies, style_blocks, svg_internals,
//            comment_nodes} }
//
// node = { tag, attrs, text?, full_text?, dims?, children: [node] }
//   text      — the element's own text, whitespace collapsed
//   full_text — text from children, for elements whose label can live in a child
//   dims      — an image's rendered and intrinsic size, when available
//
// Invariant: keep this policy-free. All the keep/drop decisions belong in
// Python (crawler/distill.py), which is what makes them testable without a
// browser.

(MAX_DATA_URI, MAX_TEXT) => {
  const dropped = {
    script_bodies: 0,
    style_blocks: 0,
    svg_internals: 0,
    comment_nodes: 0,
  };

  // Comments are counted across the whole document, not during the walk — many
  // of them sit outside the element tree we recurse over.
  try {
    const cw = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT, null);
    while (cw.nextNode()) dropped.comment_nodes++;
  } catch (e) {
    /* count zero rather than fail the capture */
  }

  const collapse = (s) => (s || "").replace(/\s+/g, " ").trim();
  const clamp = (s) => (s.length > MAX_TEXT ? s.slice(0, MAX_TEXT) : s);

  const NAME_CARRIERS = new Set([
    "a", "button", "label", "summary", "option", "legend", "th", "td",
    "h1", "h2", "h3", "h4", "h5", "h6",
  ]);

  // The element's own text, ignoring anything inside child elements.
  function ownText(el) {
    let out = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue;
    }
    return collapse(out);
  }

  // Every attribute, with oversized values trimmed.
  function attrsOf(el) {
    const out = {};
    const attrs = el.attributes;
    for (let i = 0; i < attrs.length; i++) {
      const name = attrs[i].name;
      let value = attrs[i].value == null ? "" : attrs[i].value;
      // Big data: URIs are dropped but keep their prefix, so it's still clear
      // there was an inline payload here.
      if (value.length > MAX_DATA_URI && /^\s*data:/i.test(value)) {
        const comma = value.indexOf(",");
        const head = comma === -1 ? "data:" : value.slice(0, comma + 1);
        value = head + "[dropped " + value.length + " bytes]";
      } else if (value.length > MAX_TEXT) {
        value = value.slice(0, MAX_TEXT) + "…";
      }
      out[name] = value;
    }
    return out;
  }

  // An image's rendered and intrinsic size, or null if neither is available.
  function dimsOf(el) {
    try {
      const rect = el.getBoundingClientRect();
      const rendered = [Math.round(rect.width), Math.round(rect.height)];
      const intrinsic = [el.naturalWidth || 0, el.naturalHeight || 0];
      if (!intrinsic[0] && !rendered[0]) return null;
      return { rendered: rendered, intrinsic: intrinsic };
    } catch (e) {
      return null;
    }
  }

  // Turn one element and everything under it into a node.
  function walk(el, insideSvg) {
    const tag = (el.tagName || "").toLowerCase();
    const node = { tag: tag, attrs: attrsOf(el), children: [] };

    if (tag === "style") {
      dropped.style_blocks++;
      return node; // the CSS body is never carried
    }

    if (tag === "script") {
      const type = (el.getAttribute("type") || "").toLowerCase();
      const body = el.textContent || "";
      if (body.trim()) dropped.script_bodies++;
      // JSON-LD is structured data rather than code, so it's kept verbatim.
      if (type === "application/ld+json" && body.trim()) {
        node.text = clamp(body.trim());
      }
      return node;
    }

    const own = ownText(el);
    if (own) node.text = clamp(own);

    if (NAME_CARRIERS.has(tag) || el.hasAttribute("role") || el.hasAttribute("tabindex")) {
      const full = collapse(el.textContent);
      if (full && full !== own) node.full_text = clamp(full);
    }

    if (tag === "img") {
      const d = dimsOf(el);
      if (d) node.dims = d;
    }

    if (tag === "svg") {
      // Keep the svg element, count its internals. The walk is only for the
      // count, so nested <symbol>/<use> trees are included.
      let n = 0;
      const stack = Array.prototype.slice.call(el.children);
      while (stack.length) {
        const child = stack.pop();
        n++;
        for (let i = 0; i < child.children.length; i++) stack.push(child.children[i]);
      }
      dropped.svg_internals += n;
      return node;
    }

    for (let i = 0; i < el.children.length; i++) {
      node.children.push(walk(el.children[i], insideSvg));
    }
    return node;
  }

  return { raw: walk(document.documentElement, false), dropped: dropped };
}
