"""Generate optimised logo variants, favicons and the default social image from static/brand/*.png.

Run after replacing the master logos:  python scripts/build_brand_assets.py
Masters: logo-transparent.png (dark book + wordmark, for light backgrounds) and logo-on-dark.png (white).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

BRAND = Path(__file__).resolve().parent.parent / "static" / "brand"
BLACK = (10, 10, 10)  # --rlm-black
CREAM = (255, 248, 242)  # warm off-white


def trim(img: Image.Image) -> Image.Image:
    return img.crop(img.getchannel("A").getbbox())


def square(img: Image.Image, pad: float = 0.0, bg: tuple[int, ...] | None = None) -> Image.Image:
    side = int(max(img.size) * (1 + pad * 2))
    canvas = Image.new("RGBA", (side, side), (*bg, 255) if bg else (0, 0, 0, 0))
    canvas.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))
    return canvas


def save_webp(img: Image.Image, name: str, width: int) -> None:
    out = ImageOps.contain(img, (width, width * 4), Image.LANCZOS)
    out.save(BRAND / name, "WEBP", quality=88, method=6)


def main() -> None:
    light = Image.open(BRAND / "logo-transparent.png").convert("RGBA")
    dark = Image.open(BRAND / "logo-on-dark.png").convert("RGBA")

    # Full logo (mark + wordmark)
    for w in (160, 320, 640):
        save_webp(trim(light), f"logo-transparent-{w}.webp", w)
        save_webp(trim(dark), f"logo-on-dark-{w}.webp", w)

    # Mark only (flame + book), above the gap before the wordmark (rows 0-1065)
    mark_light = trim(light.crop((0, 0, light.width, 1066)))
    mark_dark = trim(dark.crop((0, 0, dark.width, 1066)))
    for w in (64, 128, 256):
        save_webp(square(mark_light), f"mark-light-{w}.webp", w)
        save_webp(square(mark_dark), f"mark-dark-{w}.webp", w)

    # Favicons: flame + book on a black rounded tile is legible on light AND dark browser tabs.
    tile = square(mark_dark, pad=0.12, bg=BLACK)
    tile.save(BRAND / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    ImageOps.contain(tile, (32, 32), Image.LANCZOS).save(BRAND / "favicon-32.png", optimize=True)
    for size, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        ImageOps.contain(tile, (size, size), Image.LANCZOS).convert("RGB").save(BRAND / name, optimize=True)
    maskable = square(mark_dark, pad=0.25, bg=BLACK)
    ImageOps.contain(maskable, (512, 512), Image.LANCZOS).convert("RGB").save(
        BRAND / "icon-maskable-512.png", optimize=True
    )

    # Default Open Graph image 1200x630: dark logo centred on brand black.
    og = Image.new("RGB", (1200, 630), BLACK)
    logo = ImageOps.contain(trim(dark), (480, 500), Image.LANCZOS)
    og.paste(logo, ((1200 - logo.width) // 2, (630 - logo.height) // 2), logo)
    og.save(BRAND / "og-default.jpg", quality=86, optimize=True, progressive=True)

    # Placeholder image for content without photos: cream tile with the light mark, clearly generic.
    ph = Image.new("RGB", (1600, 1000), CREAM)
    m = ImageOps.contain(mark_light, (360, 360), Image.LANCZOS)
    ph.paste(m, ((1600 - m.width) // 2, (1000 - m.height) // 2), m)
    for w in (480, 960, 1600):
        ImageOps.contain(ph, (w, w), Image.LANCZOS).save(BRAND / f"placeholder_w{w}.webp", "WEBP", quality=70)
    print("Brand assets written to", BRAND)


if __name__ == "__main__":
    main()
