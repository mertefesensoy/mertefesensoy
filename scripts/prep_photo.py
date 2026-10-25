#!/usr/bin/env python3
"""Prepare the profile portrait for the tiered ASCII render.

Input: ``assets/profile-source.jpg``, a 1400 px square crop of the original
photograph (subject left of centre, patterned wallpaper behind).
Output: ``assets/profile-prepped.png``, a 900 px grayscale portrait with the
background lifted to pure white so the ASCII renderer maps it to spaces.

The output is static and regenerated only when the source changes:

    python scripts/prep_photo.py

Contract of ``prepare_portrait``: takes the source path, returns an ``L``
mode image of ``WORK_SIZE`` pixels.  Side effects: none.  Invariant: pixels at
255 are background; everything below is subject, tone-mapped so that six
luminance tiers are all populated (the renderer relies on this spread).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "profile-source.jpg"
DEFAULT_OUTPUT = ROOT / "assets" / "profile-prepped.png"

WORK_SIZE = 900
GRABCUT_ITERATIONS = 8

# Seeds as fractions of the square frame.  They describe the known composition
# of the source crop (head upper-centre, torso continuing off the lower edge)
# and must be revisited if the source photograph changes.
DEFINITE_FOREGROUND = (
    # (cx, cy, rx, ry)
    (0.49, 0.64, 0.085, 0.11),  # face
    (0.44, 0.47, 0.11, 0.055),  # hair
    (0.50, 0.95, 0.22, 0.09),  # suit and tie
)
PROBABLE_FOREGROUND = (
    (0.47, 0.60, 0.19, 0.25),  # whole head
    (0.50, 0.92, 0.36, 0.26),  # shoulders
)
# Rows above this fraction and columns outside this band are definite background.
BACKGROUND_TOP = 0.34
BACKGROUND_LEFT = 0.16
BACKGROUND_RIGHT = 0.80


def _ellipse(canvas: np.ndarray, spec: tuple[float, float, float, float], value: int) -> None:
    height, width = canvas.shape
    cx, cy, rx, ry = spec
    cv2.ellipse(
        canvas,
        (int(width * cx), int(height * cy)),
        (max(3, int(width * rx)), max(3, int(height * ry))),
        0,
        0,
        360,
        value,
        -1,
    )


def segment_subject(rgb: np.ndarray) -> np.ndarray:
    """Return a float mask in [0, 1] of the subject, 1 inside."""

    height, width = rgb.shape[:2]
    segmentation = np.full((height, width), cv2.GC_PR_BGD, dtype=np.uint8)
    segmentation[: int(height * BACKGROUND_TOP), :] = cv2.GC_BGD
    segmentation[:, : int(width * BACKGROUND_LEFT)] = cv2.GC_BGD
    segmentation[:, int(width * BACKGROUND_RIGHT) :] = cv2.GC_BGD
    for spec in PROBABLE_FOREGROUND:
        _ellipse(segmentation, spec, cv2.GC_PR_FGD)
    for spec in DEFINITE_FOREGROUND:
        _ellipse(segmentation, spec, cv2.GC_FGD)

    cv2.setRNGSeed(0)
    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        rgb,
        segmentation,
        None,
        background_model,
        foreground_model,
        GRABCUT_ITERATIONS,
        cv2.GC_INIT_WITH_MASK,
    )
    mask = np.where(
        (segmentation == cv2.GC_FGD) | (segmentation == cv2.GC_PR_FGD), 1.0, 0.0
    ).astype(np.float32)

    # Keep the largest connected component: the wallpaper's gold medallions can
    # survive GrabCut as islands, and the subject is one connected shape.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8))
    if count > 2:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        mask = (labels == largest).astype(np.float32)

    # Close small holes (collar, tie knot highlights) without moving the edge.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    coverage = float(mask.mean())
    if not 0.18 <= coverage <= 0.70:
        raise RuntimeError(
            f"subject mask covers {coverage:.0%} of the frame; the seeds no longer "
            "match the source photograph"
        )
    # A soft edge of about two output cells keeps the silhouette from aliasing.
    return cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, width / 450))


def tone_map(gray: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Spread the subject's tones so the six ASCII tiers are all used."""

    clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8))
    local = clahe.apply(gray)
    # Mild unsharp mask: the renderer samples at 150 cells across, so detail
    # finer than about 6 px is lost anyway; this keeps the ear, eye and nose.
    blur = cv2.GaussianBlur(local, (0, 0), sigmaX=2.2)
    sharpened = cv2.addWeighted(local, 1.45, blur, -0.45, 0)

    subject = sharpened[mask > 0.5]
    lo, hi = np.percentile(subject, (1.0, 99.0))
    stretched = (sharpened.astype(np.float32) - lo) / max(1.0, hi - lo)
    stretched = np.clip(stretched, 0.0, 1.0)
    # Keep the brightest subject tone a step below paper white so it never
    # becomes background in the renderer's ">= 0.97 is a space" rule.
    stretched = stretched * 0.93
    return (stretched * 255.0).astype(np.float32)


def prepare_portrait(source: Path) -> Image.Image:
    """Return a grayscale portrait composited onto a white field."""

    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    if image.width != image.height:
        side = min(image.size)
        image = image.crop((0, 0, side, side))
    image = image.resize((WORK_SIZE, WORK_SIZE), Image.Resampling.LANCZOS)
    rgb = np.asarray(image)

    mask = segment_subject(rgb)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    toned = tone_map(gray, mask)

    prepared = toned * mask + 255.0 * (1.0 - mask)
    prepared = np.clip(prepared, 0, 255).astype(np.uint8)
    return Image.fromarray(prepared, mode="L")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("output", nargs="?", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    prepared = prepare_portrait(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    prepared.save(args.output, optimize=True)
    print(f"Wrote {args.output} ({prepared.width}x{prepared.height})")


if __name__ == "__main__":
    main()
