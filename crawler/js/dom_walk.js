// Raw DOM serializer. Deliberately policy-free: it decides nothing about what is
// worth keeping, it only produces a faithful, JSON-safe mirror of the document
// plus the counts of the four things it refuses to carry (script bodies, style
// blocks, svg internals, comments). Every keep/drop rule in spec §5 is applied
// in Python against this output, which is what makes distillation unit-testable
// without a browser and byte-reproducible from a single capture.
//
// Returns: { raw: <node>, dropped: {script_bodies, style_blocks, svg_internals,
//            comment_nodes} }
//
// node ::= { tag, attrs, text?, full_text?, dims?, children: [node] }
//   text      — own text nodes only, whitespace-collapsed (verbatim for JSON-LD)
//   full_text — descendant text, bounded; emitted only where an accessible name
//               can live in a child element (button > span > "Add to cart")
//   dims      — img rendered vs intrinsic, when obtainable

(MAX_DATA_URI, MAX_TEXT) => {
  const dropped = {
    script_bodies: 0,
    style_blocks: 0,
    svg_internals: 0,
    comment_nodes: 0,
  };

  // Comments are counted document-wide rather than during the walk: they live
  // outside the element tree we recurse over (head, between siblings, inside
  // <template>) and undercounting here would misreport absence as omission.
  try {
    const cw = document.createTreeWalker(document, NodeFilter.SHOW_COMMENT, null);
    while (cw.nextNode()) dropped.comment_nodes++;
  } catch (e) {
    /* counted as zero rather than failing the capture */
  }

  const collapse = (s) => (s || "").replace(/\s+/g, " ").trim();
  const clamp = (s) => (s.length > MAX_TEXT ? s.slice(0, MAX_TEXT) : s);

  const NAME_CARRIERS = new Set([
    "a", "button", "label", "summary", "option", "legend", "th", "td",
    "h1", "h2", "h3", "h4", "h5", "h6",
  ]);

  function ownText(el) {
    let out = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue;
    }
    return collapse(out);
  }

  function attrsOf(el) {
    const out = {};
    const attrs = el.attributes;
    for (let i = 0; i < attrs.length; i++) {
      const name = attrs[i].name;
      let value = attrs[i].value == null ? "" : attrs[i].value;
      // Data-URI payloads over 1KB are dropped in place (spec §5). The prefix is
      // retained so the fact that it *was* an inline payload stays legible.
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

  function walk(el, insideSvg) {
    const tag = (el.tagName || "").toLowerCase();
    const node = { tag: tag, attrs: attrsOf(el), children: [] };

    if (tag === "style") {
      dropped.style_blocks++;
      return node; // body never carried
    }

    if (tag === "script") {
      const type = (el.getAttribute("type") || "").toLowerCase();
      const body = el.textContent || "";
      if (body.trim()) dropped.script_bodies++;
      // JSON-LD is structured data, not a script body — kept verbatim (spec §5).
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
      // The svg element itself is kept (Python decides); its internals are only
      // counted. Recursing purely to count keeps the number honest for nested
      // <symbol>/<use> trees.
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
