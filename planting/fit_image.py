"""Re-encode an image to a target wire size, keeping the picture itself.

    python planting/fit_image.py product-packs-cards.jpg --target-kb 300
    python planting/fit_image.py photo.jpg --target-kb 300 --max-width 2000

The PDP featured image is served verbatim - a master URL with no transform
params, so the CDN never transcodes it. The uploaded file's bytes are the wire
bytes, which makes an LCP target a byte budget. This bisects JPEG quality to
hit that budget while the store keeps its real product photo; obviously
synthetic art on a golden entry reads as a test harness.

Prints the input's hash as well as the output's, since the input photo isn't
generated and a hash of something unrecoverable isn't provenance.

Sizing only - measure.py decides when to stop.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
from pathlib import Path

from PIL import Image


def encode(img: Image.Image, quality: int) -> bytes:
    """Encode an image to JPEG bytes at the given quality."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: fit one image to a target size and write it out."""
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("input", type=Path)
    p.add_argument("--target-kb", type=float, required=True,
                   help="Encoded size to aim for, in KB")
    p.add_argument("--max-width", type=int, default=None,
                   help="Downscale first if wider (keeps aspect; only shrinks)")
    p.add_argument("--min-quality", type=int, default=35,
                   help="Never go below this JPEG quality (default 35) - artifacts on a product photo break realism; downscale instead")
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
