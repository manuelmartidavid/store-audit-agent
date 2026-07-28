"""Generate the oversized hero PNG for golden entry 02, defect P-01.

    python planting/make_hero_p01.py                       # 3200x2132, ~1.9 MB
    python planting/make_hero_p01.py --target-mb 4         # heavier, slower LCP
    python planting/make_hero_p01.py --width 2400          # lighter than the floor

P-01 aims home LCP past 4.0s (target >= 5s) by shipping an unoptimised
full-resolution hero. The defect is *weight*, not appearance: the store must
still look like a normal store, or a human reviewing the golden entry reads the
page as broken rather than slow.

Two constraints come from the baseline capture (fixtures/02, slide 1):

  declared dimensions 800x533  ->  aspect 1.500938
  alt "Shop the finest trading cards", loading="eager"

The output preserves that aspect EXACTLY (4x -> 3200x2132) so replacing the
asset cannot move layout. P-03 owns CLS on the collection template; if this
image changed the hero's aspect ratio it would inject shift on home too and
contaminate a metric that is supposed to stay at baseline.

Size is reached by bisecting sparse film grain against the encoded byte count —
grain is what actually defeats PNG's DEFLATE, the same reason a real merchant's
photo-exported-as-PNG is huge. The floor at a given width comes from rendering
the plate at reduced detail and upscaling; below that floor, drop --width.

This script sizes the asset. It does not decide whether P-01 landed:
run planting/measure.py after uploading, and let the recaptured fixture label.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# Default source aspect: baseline slide 1, read out of fixtures/02/crawl.json.
# Do not "tidy" these — they are the P-01 home-hero ratio. P-02 targets the PDP
# featured image, whose ratio is different (1366x2049 ~ 0.667, 1366x907 ~ 1.506,
# 1366x1004 ~ 1.361 in the baseline); pass it with --aspect W:H or --height.
BASE_W, BASE_H = 800, 533


def _linear_gradient(w: int, h: int) -> np.ndarray:
    """Dark slate backdrop with a warm off-centre spotlight."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xn, yn = xx / w, yy / h

    top = np.array([18, 24, 38], np.float32)
    bottom = np.array([8, 10, 16], np.float32)
    base = top[None, None, :] * (1 - yn[..., None]) + bottom[None, None, :] * yn[..., None]

    # Spotlight behind where the card fan sits, right of the text column.
    cx, cy, r = 0.66, 0.52, 0.60
    d = np.sqrt(((xn - cx) * 1.35) ** 2 + (yn - cy) ** 2) / r
    glow = np.clip(1.0 - d, 0.0, 1.0) ** 2.2
    warm = np.array([196, 132, 58], np.float32)
    base += glow[..., None] * warm[None, None, :] * 0.85

    # Vignette.
    vd = np.sqrt((xn - 0.5) ** 2 + ((yn - 0.5) * 0.8) ** 2) / 0.78
    base *= np.clip(1.15 - vd**2 * 0.55, 0.35, 1.15)[..., None]
    return np.clip(base, 0, 255)


def _holo(w: int, h: int, phase: float) -> Image.Image:
    """A card face: diagonal holographic sweep over a deep base."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (xx / w + yy / h) * 2.6 + phase
    r = 118 + 58 * np.sin(t)
    g = 112 + 58 * np.sin(t + 2.09)
    b = 124 + 58 * np.sin(t + 4.19)
    face = np.dstack([r, g, b]).astype(np.float32)

    # Darken toward the bottom so the fan reads as lit from above.
    face *= np.clip(1.05 - (yy / h) * 0.45, 0.4, 1.05)[..., None]
    # Specular band.
    band = np.exp(-(((xx / w) - 0.34) ** 2) / 0.012)
    face += band[..., None] * 46
    return Image.fromarray(np.clip(face, 0, 255).astype(np.uint8), "RGB")


def _card(w: int, h: int, phase: float, angle: float) -> Image.Image:
    """One rounded, bordered, rotated card with an alpha channel."""
    ss = 2  # supersample so the rotated edges stay clean
    cw, ch = w * ss, h * ss
    face = _holo(cw, ch, phase)

    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=int(min(cw, ch) * 0.055), fill=255)

    draw = ImageDraw.Draw(face)
    inset = int(min(cw, ch) * 0.045)
    draw.rounded_rectangle(
        [inset, inset, cw - 1 - inset, ch - 1 - inset],
        radius=int(min(cw, ch) * 0.035),
        outline=(238, 236, 230),
        width=max(2, int(min(cw, ch) * 0.012)),
    )
    # Suggestion of a photo window, no text — the theme overlays its own copy.
    win = [inset * 3, inset * 3, cw - 1 - inset * 3, int(ch * 0.62)]
    draw.rounded_rectangle(win, radius=int(min(cw, ch) * 0.02), fill=(26, 30, 44))
    draw.ellipse(
        [win[0] + (win[2] - win[0]) * 0.28, win[1] + (win[3] - win[1]) * 0.22,
         win[0] + (win[2] - win[0]) * 0.72, win[1] + (win[3] - win[1]) * 0.86],
        fill=(58, 70, 96),
    )

    card = face.convert("RGBA")
    card.putalpha(mask)
    card = card.resize((w, h), Image.LANCZOS)
    return card.rotate(angle, resample=Image.BICUBIC, expand=True)


def build_artwork(w: int, h: int, detail: float) -> Image.Image:
    """Render at `detail` x the output size, then upscale to (w, h).

    Merchants who ship 3000px heroes very often upscaled a smaller original, and
    an upscaled plate carries far less high-frequency content — which is the only
    lever that moves PNG size *downward* at fixed dimensions. Rendering natively
    at 3200px floors the file around 5.5 MB (~27s of slow-4G transfer), which
    overshoots P-01's aim so far the page reads as broken rather than slow.
    """
    bw = max(320, int(w * detail))
    bh = round(bw * h / w)
    return build_base(bw, bh).resize((w, h), Image.LANCZOS)


def build_base(w: int, h: int) -> Image.Image:
    canvas = Image.fromarray(_linear_gradient(w, h).astype(np.uint8), "RGB")

    # Bokeh — cheap depth, compresses well, keeps the plate from looking flat.
    bok = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bok)
    rng = np.random.default_rng(20260724)  # fixed: the asset must be reproducible
    for _ in range(26):
        r = int(rng.integers(w // 80, w // 26))
        cx = int(rng.integers(0, w))
        cy = int(rng.integers(0, h))
        a = int(rng.integers(10, 30))
        bd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 205, 140, a))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), bok.filter(ImageFilter.GaussianBlur(w // 220)))

    # The fan: seven cards arcing across the right two-thirds.
    n = 7
    card_h = int(h * 0.50)
    card_w = int(card_h * 0.715)  # standard trading-card ratio 2.5 x 3.5
    for i in range(n):
        f = i / (n - 1)
        angle = 22 - f * 44
        card = _card(card_w, card_h, phase=f * 1.9, angle=angle)
        cx = int(w * (0.475 + f * 0.395))
        cy = int(h * (0.56 + math.sin(f * math.pi) * -0.06))
        pos = (cx - card.width // 2, cy - card.height // 2)

        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        shadow.paste(Image.new("RGBA", card.size, (0, 0, 0, 120)), (pos[0] + int(w * 0.006), pos[1] + int(h * 0.014)), card)
        canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(w // 260)))

        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        layer.paste(card, pos, card)
        canvas = Image.alpha_composite(canvas, layer)

    return canvas.convert("RGB")


def _encode(arr: np.ndarray, level: int) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG", compress_level=level, optimize=False)
    return buf.getvalue()


GRAIN_SIGMA = 6.0


def grain(base: np.ndarray, density: float, seed: int = 7) -> np.ndarray:
    """Perturb `density` of pixels, leaving the rest byte-identical.

    Amplitude is the wrong knob: Gaussian noise over *every* pixel defeats PNG's
    row filters all at once, so sigma 0.04 and sigma 0.3 both land near 5.5 MB
    and the size curve is a step, not a ramp. Sparse grain keeps the untouched
    pixels perfectly filterable, so encoded size tracks density smoothly and the
    bisection can actually hit a target.
    """
    if density <= 0:
        return base.astype(np.uint8)
    rng = np.random.default_rng(seed)
    out = base.astype(np.float32)
    mask = rng.random(base.shape[:2]) < density
    noise = rng.normal(0.0, GRAIN_SIGMA, (int(mask.sum()), base.shape[2])).astype(np.float32)
    out[mask] += noise
    return np.clip(out, 0, 255).astype(np.uint8)


def _parse_aspect(spec: str) -> tuple[int, int]:
    """`W:H` -> (W, H), positive integers. The source ratio to preserve."""
    if ":" not in spec:
        raise argparse.ArgumentTypeError("aspect must look like W:H, e.g. 1366:2049")
    w_s, _, h_s = spec.partition(":")
    try:
        aw, ah = int(w_s), int(h_s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"aspect ends must be integers: {spec!r}")
    if aw <= 0 or ah <= 0:
        raise argparse.ArgumentTypeError(f"aspect ends must be positive: {spec!r}")
    return aw, ah


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--target-mb", type=float, default=1.9,
                   help="Target encoded size in MB (default 1.9; P-01 aims >=5s LCP, P-02 aims 3.0-3.8s so start ~0.5 and bisect)")
    p.add_argument("--width", type=int, default=BASE_W * 4, help="Output width (default 3200 = 4x baseline)")
    p.add_argument("--aspect", type=_parse_aspect, default=(BASE_W, BASE_H), metavar="W:H",
                   help="Source ratio to preserve exactly (default 800:533, the P-01 home hero). "
                        "For P-02 pass the PDP featured image's ratio, e.g. 1366:2049.")
    p.add_argument("--height", type=int, default=None,
                   help="Explicit output height in px. Overrides --aspect derivation (use exact source pixels).")
    p.add_argument("--detail", type=float, default=0.35, help="Render scale before upscaling (lowers the size floor)")
    p.add_argument("--seed", type=int, default=7,
                   help="Grain RNG seed (default 7). Recorded with the sha256 so a sized asset is reproducible.")
    p.add_argument("--compress-level", type=int, default=6, help="zlib level; 6 is what an export tool would emit")
    p.add_argument("--out", type=Path, default=Path("hero-slide-1-3200.png"))
    args = p.parse_args(argv)

    w = args.width
    aw, ah = args.aspect
    if args.height is not None:
        # Explicit pixels: the user owns the ratio. Still report what it is.
        h = args.height
        if h <= 0:
            p.error("--height must be positive")
    else:
        # A rounding-induced 1px letterbox is CLS this asset must not introduce
        # (P-03 owns CLS for this entry), so require the ratio to divide exactly
        # rather than rounding and warning.
        if (w * ah) % aw:
            p.error(
                f"width {w} does not divide cleanly by aspect {aw}:{ah} "
                f"(height would be {w * ah / aw:.4f}px). Pick a width divisible by {aw}, "
                f"or pass an explicit --height."
            )
        h = w * ah // aw
        # Exact-ratio guarantee: w/h reduces to the source ratio with no drift.
        assert w * ah == h * aw, "aspect assertion failed"

    print(f"building {w}x{h} (source aspect {aw}:{ah} = {aw/ah:.6f}, output {w/h:.6f})")
    base = np.asarray(build_artwork(w, h, args.detail))

    target = int(args.target_mb * 1024 * 1024)
    floor = _encode(base, args.compress_level)
    print(f"  grain density 0.000 -> {len(floor)/1024/1024:6.3f} MB  (floor at this width/detail)")

    if len(floor) >= target:
        data, amp = floor, 0.0
    else:
        lo, hi = 0.0, 1.0
        best = (floor, 0.0)
        for _ in range(10):
            mid = (lo + hi) / 2
            candidate = _encode(grain(base, mid, args.seed), args.compress_level)
            print(f"  grain density {mid:5.3f} -> {len(candidate)/1024/1024:6.3f} MB")
            if abs(len(candidate) - target) < abs(len(best[0]) - target):
                best = (candidate, mid)
            if len(candidate) < target:
                lo = mid
            else:
                hi = mid
        data, amp = best

    args.out.write_bytes(data)
    size = len(data)
    digest = hashlib.sha256(data).hexdigest()
    print(f"\nwrote {args.out}  {size/1024/1024:.2f} MB  ({w}x{h}, grain density {amp:.3f})")
    # One provenance line: seed + byte count + sha256 make the asset reproducible
    # (decision 12). A recorded hash for an unseeded artifact fingerprints
    # something nobody can regenerate, so the seed travels with the hash.
    print(f"  provenance: seed={args.seed} bytes={size} sha256={digest}")
    if size > target * 1.12:
        want = args.width * math.sqrt(target / size)
        print(f"! floored above the target - for a lighter asset try --width {int(want // 8 * 8)}")
    # Rough slow-4G arithmetic, for aiming only. measure.py decides, the fixture labels.
    print(f"  slow-4G transfer at ~205 KB/s ~= {size/1024/205:.1f}s on top of the baseline 1.88s home LCP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
