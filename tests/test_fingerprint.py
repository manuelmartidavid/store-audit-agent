"""Fingerprinting — spec §4, and the MNC-003 rule enforced at the data layer."""

from __future__ import annotations

from crawler.fingerprint import Signals, build, empty


def test_shopify_is_detected_from_asset_urls_and_the_theme_object():
    signals = Signals(
        urls=["https://cdn.shopify.com/s/files/1/app.js", "https://shop.test/cdn/shop/t/2/a.css"],
        shopify_global=True,
        shopify_theme={"name": "Dawn", "version": "12.0.0", "role": "main"},
    )
    result = build(signals)
    assert result["platform"] == "shopify"
    assert "cdn.shopify.com asset URLs" in result["evidence"]
    assert "Shopify.theme JSON" in result["evidence"]
    assert result["theme"] == {"name": "Dawn", "version": "12.0.0"}


def test_a_theme_without_a_version_reports_a_null_version_rather_than_guessing():
    signals = Signals(urls=["https://cdn.shopify.com/x.js"], shopify_theme={"name": "Dawn"})
    assert build(signals)["theme"] == {"name": "Dawn", "version": None}


def test_theme_is_null_when_nothing_declares_one():
    signals = Signals(urls=["https://cdn.shopify.com/x.js"])
    assert build(signals)["theme"] is None


def test_woocommerce_is_detected_from_plugin_assets():
    signals = Signals(
        urls=["https://shop.test/wp-content/plugins/woocommerce/assets/js/frontend.js"],
        meta={"generator": "WooCommerce 8.2.1"},
        body_classes=["woocommerce", "woocommerce-page"],
    )
    result = build(signals)
    assert result["platform"] == "woocommerce"
    assert result["evidence"]


def test_an_observed_store_matching_nothing_known_is_custom_not_unknown():
    """Entry 04's reduced path: the crawl still completes."""
    signals = Signals(urls=["https://shop.test/static/app.js"], meta={"description": "hi"})
    assert build(signals)["platform"] == "custom"


def test_apps_are_detected_deduplicated_and_never_causally_attributed():
    signals = Signals(
        urls=[
            "https://cdn.shopify.com/x.js",
            "https://cdn.judge.me/widget.js",
            "https://cdn.judge.me/loader.js",
            "https://static.klaviyo.com/onsite/js/klaviyo.js",
        ]
    )
    apps = build(signals)["apps"]
    assert [a["name"] for a in apps] == ["Judge.me", "Klaviyo"], "sorted and deduplicated"
    assert all(a["evidence"] == "script src pattern" for a in apps)


def test_a_store_that_was_not_observed_reports_unknown_even_when_the_gate_is_shopify():
    """MNC-003: the fingerprint reports what was observed *of the store*, and the
    store was not observed. Enforced here rather than in the prompt."""
    signals = Signals(
        urls=["https://cdn.shopify.com/s/files/1/password-page.js"],
        shopify_global=True,
        shopify_theme={"name": "Dawn"},
    )
    result = build(signals, observed=False)
    assert result == empty()
    assert result["platform"] == "unknown"
    assert result["evidence"] == [] and result["theme"] is None and result["apps"] == []


def test_evidence_is_deduplicated_and_stably_ordered_across_merges():
    a = Signals(urls=["https://cdn.shopify.com/a.js"], shopify_global=True)
    b = Signals(urls=["https://cdn.shopify.com/b.js"], shopify_global=True)
    a.merge(b)
    evidence = build(a)["evidence"]
    assert len(evidence) == len(set(evidence))
    assert build(a)["evidence"] == evidence


def test_merge_keeps_the_first_theme_and_unions_the_signals():
    a = Signals(shopify_theme={"name": "Dawn"})
    a.merge(Signals(shopify_theme={"name": "Debut"}, urls=["https://cdn.shopify.com/x.js"], shopify_global=True))
    assert a.shopify_theme == {"name": "Dawn"}
    assert a.shopify_global is True


# --- theme app extensions ----------------------------------------------------
# APP_SIGNATURES can only name an app somebody already hardcoded. Extensions are
# where most of a modern store's third-party surface actually lives, and naming
# them is what makes P-04's effort-floor framing (and MNC-002) testable.

EXT = "https://cdn.shopify.com/extensions/019f7be7-1888-7854-bf22-91e9942504c2"


def test_an_extension_asset_path_names_the_app_the_domain_list_has_never_heard_of():
    signals = Signals(urls=[f"{EXT}/restockrocket-1-546/assets/restockrocket-product.js"])
    assert build(signals)["apps"] == [
        {"name": "restockrocket-1", "evidence": "theme app extension asset path"}
    ]


def test_every_asset_of_one_extension_collapses_to_one_app():
    signals = Signals(
        urls=[
            f"{EXT}/restockrocket-1-546/assets/restockrocket-product.js",
            f"{EXT}/restockrocket-1-546/assets/restockrocket-collection.js",
            f"{EXT}/restockrocket-1-546/assets/style.css",
        ]
    )
    assert [a["name"] for a in build(signals)["apps"]] == ["restockrocket-1"]


def test_only_the_trailing_build_counter_is_stripped_from_the_handle():
    """`multilocation-2-549` is handle `multilocation-2`, build 549. Stripping
    the `-2` as well would rename somebody's app."""
    uuid = "019f6fd1-84d2-7d66-baed-27e44cfaf6c8"
    signals = Signals(
        urls=[
            f"https://cdn.shopify.com/extensions/{uuid}/multilocation-2-549/assets/popup.js",
            f"{EXT}/forms-2473/assets/index.js",
            f"{EXT}/ez-terms-and-conditions-checkbox-167/assets/terms.js",
        ]
    )
    assert [a["name"] for a in build(signals)["apps"]] == [
        "ez-terms-and-conditions-checkbox",
        "forms",
        "multilocation-2",
    ]


def test_the_handle_is_reported_verbatim_including_its_typos():
    """`inventory-info-theme-exrtensions` is what the store serves. Correcting it
    would be inventing a product name the capture does not support."""
    signals = Signals(urls=[f"{EXT}/inventory-info-theme-exrtensions-232/assets/main.bundle.js"])
    assert build(signals)["apps"][0]["name"] == "inventory-info-theme-exrtensions"


def test_an_extensions_path_without_a_uuid_is_not_an_app():
    """No guessing: a path that doesn't match the convention names nothing."""
    signals = Signals(
        urls=[
            "https://shop.test/extensions/not-a-uuid/some-app-12/assets/a.js",
            "https://shop.test/assets/extensions/theme-extensions-4/x.js",
        ]
    )
    assert build(signals)["apps"] == []


def test_one_app_seen_on_its_domain_and_as_an_extension_is_one_entry():
    signals = Signals(
        urls=[
            "https://cdn.judge.me/widget.js",
            f"{EXT}/judgeme-core-14/assets/loader.js",
        ]
    )
    apps = build(signals)["apps"]
    assert apps == [
        {
            "name": "Judge.me",
            "evidence": "script src pattern + theme app extension asset path",
        }
    ], "the vendor display name wins; the handle folds into it"


def test_an_unrelated_extension_does_not_fold_into_a_known_app():
    signals = Signals(
        urls=["https://cdn.judge.me/widget.js", f"{EXT}/restockrocket-1-546/assets/a.js"]
    )
    assert [a["name"] for a in build(signals)["apps"]] == ["Judge.me", "restockrocket-1"]


def test_extension_apps_are_still_empty_for_a_store_that_was_not_observed():
    """MNC-003 again — the new detection path must not leak past the gate."""
    signals = Signals(urls=[f"{EXT}/restockrocket-1-546/assets/a.js"])
    assert build(signals, observed=False)["apps"] == []


def test_app_order_is_stable_regardless_of_url_order():
    urls = [
        f"{EXT}/multilocation-2-549/assets/a.js",
        "https://static.klaviyo.com/onsite/js/klaviyo.js",
        f"{EXT}/al-bulk-discount-manager-84/assets/bar.js",
    ]
    forward = [a["name"] for a in build(Signals(urls=list(urls)))["apps"]]
    reverse = [a["name"] for a in build(Signals(urls=list(reversed(urls))))["apps"]]
    assert forward == reverse == ["Klaviyo", "al-bulk-discount-manager", "multilocation-2"]
