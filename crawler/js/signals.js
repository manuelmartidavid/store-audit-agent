// Fingerprint signal collection. Observation only — every judgement about what
// these signals mean lives in fingerprint.py, and none of it is causal.
() => {
  const urls = [];
  const push = (u) => {
    if (u && typeof u === "string") urls.push(u);
  };

  document.querySelectorAll("script[src]").forEach((e) => push(e.getAttribute("src")));
  document.querySelectorAll("link[href]").forEach((e) => push(e.getAttribute("href")));
  document.querySelectorAll("img[src]").forEach((e) => push(e.getAttribute("src")));
  document.querySelectorAll("iframe[src]").forEach((e) => push(e.getAttribute("src")));

  const inline = [];
  document.querySelectorAll("script:not([src])").forEach((e) => {
    const body = e.textContent || "";
    if (body.trim()) inline.push(body.slice(0, 4000));
  });

  const meta = {};
  document.querySelectorAll("meta[name][content]").forEach((e) => {
    const name = (e.getAttribute("name") || "").toLowerCase();
    if (name && !(name in meta)) meta[name] = e.getAttribute("content");
  });

  let theme = null;
  let shopifyGlobal = false;
  try {
    if (window.Shopify) {
      shopifyGlobal = true;
      if (window.Shopify.theme && typeof window.Shopify.theme === "object") {
        theme = JSON.parse(JSON.stringify(window.Shopify.theme));
      }
    }
  } catch (e) {
    theme = null;
  }

  return {
    urls: urls.slice(0, 400),
    inline_scripts: inline.slice(0, 40),
    meta: meta,
    shopify_global: shopifyGlobal,
    shopify_theme: theme,
    body_classes: document.body ? Array.prototype.slice.call(document.body.classList) : [],
  };
}
