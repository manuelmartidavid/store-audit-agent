"""Evidence pointer grammar — spec §9."""

from __future__ import annotations

from crawler import pointers
from crawler.distill import distill
from tests.rawtree import build

PDP = """
<html><body>
  <header id="shopify-section-template--1__header"><nav role="navigation">
    <a href="/collections/cards">Cards</a></nav></header>
  <main id="MainContent">
    <h1>1986 Rookie Card</h1>
    <form action="/cart/add" id="product-form" data-section-type="product">
      <div class="btn" onclick="add()" data-testid="add-to-cart">Add to cart</div>
      <select name="id"><option value="1">One</option></select>
    </form>
    <ul><li><a href="/policies/refund">Refunds</a></li><li><a href="/policies/shipping">Shipping</a></li></ul>
  </main>
</body></html>
"""


def _tree(html: str = PDP):
    raw, _ = build(html)
    return distill(raw)


def _pointer_for(tree, predicate) -> str | None:
    for pointer, node in pointers.iter_paths("pdp", tree):
        if predicate(node):
            return pointer
    return None


# --- construction -----------------------------------------------------------

def test_name_priority_is_id_then_role_then_section_then_tag():
    assert pointers.segment_name({"tag": "div", "attrs": {"id": "product-form", "role": "form"}}) == "product-form"
    assert pointers.segment_name({"tag": "div", "attrs": {"role": "navigation"}}) == "navigation"
    assert pointers.segment_name({"tag": "div", "attrs": {"data-section-type": "main-product"}}) == "main-product"
    assert pointers.segment_name({"tag": "div", "attrs": {}}) == "div"


def test_shopify_section_ids_reduce_to_the_section_name():
    assert pointers.segment_name({"tag": "header", "attrs": {"id": "shopify-section-template--1__header"}}) == "header"


def test_qualifier_prefers_a_distinctive_attribute_then_a_text_slug():
    assert pointers.segment_qualifier({"tag": "div", "attrs": {"data-testid": "add-to-cart"}}) == "add-to-cart"
    assert pointers.segment_qualifier({"tag": "div", "attrs": {}, "text": "Add to cart now please"}) == "add-to-cart-now"


def test_text_slugs_are_kebab_case_and_at_most_four_words():
    assert pointers.slug("Add To  Cart, Now! Please Immediately") == "add-to-cart-now"


def test_paths_are_shallow_and_anchored_at_the_nearest_named_section():
    """`pdp/product-form/div[add-to-cart]`, not a twelve-segment tag chain."""
    pointer = _pointer_for(_tree(), lambda n: n["attrs"].get("data-testid") == "add-to-cart")
    assert pointer == "crawl:pdp/product-form/div[add-to-cart]"


def test_an_id_derived_name_takes_no_qualifier():
    assert pointers.segment({"tag": "form", "attrs": {"id": "product-form", "data-section-type": "product"}}) == "product-form"


def test_index_qualifiers_are_a_last_resort_for_otherwise_identical_siblings():
    tree = _tree('<html><body><main><span tabindex="0"></span><span tabindex="0"></span></main></body></html>')
    seen = [p for p, n in pointers.iter_paths("pdp", tree) if n.get("tag") == "span"]
    assert seen == ["crawl:pdp/main/span[1]", "crawl:pdp/main/span[2]"]


# --- normalized matching ----------------------------------------------------

def test_matching_is_case_insensitive():
    assert pointers.matches("crawl:pdp/Product-Form/DIV[Add-To-Cart]", "crawl:pdp/product-form/div[add-to-cart]")


def test_index_qualifiers_are_ignored_when_the_unindexed_path_is_unambiguous():
    assert pointers.matches("crawl:pdp/main/ul/li[2]", "crawl:pdp/main/ul/li")


def test_matching_falls_back_to_suffix_when_the_anchor_differs():
    """The model anchored at product-form, the label at main/product-form."""
    assert pointers.matches("crawl:pdp/product-form/div[add-to-cart]",
                            "crawl:pdp/main/product-form/div[add-to-cart]")


def test_a_different_template_never_matches():
    assert not pointers.matches("crawl:home/product-form/div[add-to-cart]",
                                "crawl:pdp/product-form/div[add-to-cart]")


def test_a_different_namespace_never_matches():
    assert not pointers.matches("axe:button-name", "crawl:pdp/button-name")


def test_an_unrelated_path_does_not_match():
    assert not pointers.matches("crawl:pdp/footer/input[email]", "crawl:pdp/product-form/div[add-to-cart]")


# --- resolution (automatic-fail #2) ----------------------------------------

def _crawl_fixture():
    return {"templates": {"pdp": {"status": "captured", "distilled": _tree()}}}


def test_a_constructed_pointer_resolves_back_to_its_node():
    crawl = _crawl_fixture()
    node = pointers.resolve("crawl:pdp/product-form/div[add-to-cart]", crawl)
    assert node is not None and node["attrs"]["onclick"] == "add()"


def test_a_plausible_but_invented_pointer_does_not_resolve():
    """This is what makes automatic-fail #2 mechanically checkable."""
    assert pointers.resolve("crawl:pdp/product-form/button[buy-it-now]", _crawl_fixture()) is None


def test_pointers_into_an_uncaptured_template_do_not_resolve():
    crawl = {"templates": {"pdp": {"status": "blocked", "distilled": None}}}
    assert pointers.resolve("crawl:pdp/anything", crawl) is None


def test_every_pointer_the_crawler_can_construct_resolves_to_its_own_node():
    """Round-trip: construction and resolution agree on every node in the tree."""
    crawl = _crawl_fixture()
    tree = crawl["templates"]["pdp"]["distilled"]
    for pointer, node in pointers.iter_paths("pdp", tree):
        assert pointers.resolve(pointer, crawl) is not None, pointer
