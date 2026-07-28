"""Re-encode an image to a target wire size, preserving its content.

    python planting/fit_image.py product-packs-cards.jpg --target-kb 300
    python planting/fit_image.py photo.jpg --target-kb 300 --max-width 2000

P-02's knob. The PDP featured image is served VERBATIM (master URL, no
transform params -> no CDN transcode; verified 2026-07-27: 1562 KB jpeg on the
wire while its width-transformed siblings arrived as 51-65 KB webp). So the
uploaded file's bytes ARE the wire bytes, and hitting an LCP window means
hitting a byte budget. This bisects JPEG quality against the encoded size, so
the store keeps its real product photo - realism matters on a golden entry;
a PDP with obviously synthetic art reads as a test harness.

Prints seed-free provenance (bytes + sha256): unlike the P-01 grain plate the
input photo is not generated, so the input file's own hash travels alongside
the output's (decision 12 - a hash of something unrecoverable is not provenance).

Sizing only. measure.py decides when to stop; the recaptured fixture labels.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

from PIL import Image


def encode(img: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path)
    p.add_argument("--target-kb", type=float, required=True,
                   help="Encoded size to aim for. P-02: ~250-350 (baseline PDP was 2.33s on ~65 KB; the 3.0-3.8s window affords ~+225 KB)")
    p.add_argument("--max-width", type=int, default=None,
                   help="Downscale first if wider (keeps aspect exactly; only shrinks, never enlarges)")
    p.add_argument("--min-quality", type=int, default=35,
                   help="Refuse to go below this JPEG quality (default 35) - visible artifacts on a product photo break golden-entry realism; downscale instead")
    p.add_argument("--out", type=Path, default=None, help="Default: <input>-fitted.jpg")
    args = p.parse_args(argv)

    raw = args.input.read_bytes()
    src_sha = hashlib.sha256(raw).hexdigest()
    img = Image.open(io.BytesIO(raw))
    img = img.convert("RGB")
    w0, h0 = img.size

    if args.max_width and img.width > args.max_width:
        nw = args.max_width
        nh = round(img.height * nw / img.width)
        img = img.resize((nw, nh), Image.LANCZOS)

    target = int(args.target_kb * 1024)
    lo, hi = args.min_quality, 95
    best: tuple[bytes, int] | None = None
    for _ in range(8):
        q = (lo + hi) // 2
        data = encode(img, q)
        print(f"  quality {q:2d} -> {len(data)/1024:7.1f} KB")
        if best is None or abs(len(data) - target) < abs(len(best[0]) - target):
            best = (data, q)
        if len(data) > target:
            hi = q - 1
        else:
            lo = q + 1
        if lo > hi:
            break

    assert best is not None
    data, q = best
    if len(data) > target * 1.15 and q <= args.min_quality:
        print(f"! floor: quality {q} still {len(data)/1024:.0f} KB - re-run with --max-width "
              f"{int(img.width * (target / len(data)) ** 0.5 // 8 * 8)} to shrink pixels instead")

    out = args.out or args.input.with_name(args.input.stem + "-fitted.jpg")
    out.write_bytes(data)
    print(f"\nwrote {out}  {len(data)/1024:.1f} KB  quality {q}  {img.width}x{img.height}"
          f"{'' if img.size == (w0, h0) else f' (from {w0}x{h0})'}")
    print(f"  provenance: input sha256={src_sha[:16]}... bytes={len(raw)}")
    print(f"  provenance: output sha256={hashlib.sha256(data).hexdigest()} bytes={len(data)}")
    print(f"  slow-4G wire at ~205 KB/s ~= {len(data)/1024/205:.1f}s of load time")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
