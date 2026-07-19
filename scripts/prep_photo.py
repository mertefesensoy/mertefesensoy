#!/usr/bin/env python3
"""Prepare the profile portrait for a clean, high-contrast ASCII render.

The output is intentionally static and is regenerated only when the source
portrait changes.  It uses local contrast enhancement and a soft subject mask
so the background maps to spaces in the ASCII density ramp.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "assets" / "profile-source.png"
DEFAULT_OUTPUT = ROOT / "assets" / "profile-prepped.png"


def prepare_portrait(source: Path) -> Image.Image:
    """Return a grayscale portrait composited onto a clean white field."""

    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")

    # Use a square upper-body crop so the face receives enough character cells
    # to retain the eyes, nose, mouth, hairline, collar, and lapel structure.
    crop_left = round(image.width * 0.08)
    crop_top = round(image.height * 0.12)
    crop_size = max(
        1,
        min(
            round(min(image.width, image.height) * 0.52),
            image.width - crop_left,
            image.height - crop_top,
        ),
    )
    image = image.crop(
        (crop_left, crop_top, crop_left + crop_size, crop_top + crop_size)
    )
    rgb = np.asarray(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    clahe = cv2.createCLAHE(clipLimit=2.1, tileGridSize=(6, 6))
    gray = clahe.apply(gray)
    local_blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=0.8)
    gray = cv2.addWeighted(gray, 1.35, local_blur, -0.35, 0)

    height, width = gray.shape

    # Seed OpenCV GrabCut with the known composition of the profile portrait:
    # head near the upper-left center and suit continuing to the lower edge.
    # The broad probable-foreground area lets GrabCut recover the shoulders,
    # while the small definite seeds avoid learning the wallpaper as subject.
    cv2.setRNGSeed(0)
    segmentation = np.full((height, width), cv2.GC_BGD, dtype=np.uint8)
    cv2.ellipse(
        segmentation,
        (int(width * 0.40), int(height * 0.38)),
        (max(3, int(width * 0.28)), max(3, int(height * 0.34))),
        0,
        0,
        360,
        cv2.GC_PR_FGD,
        -1,
    )
    cv2.ellipse(
        segmentation,
        (int(width * 0.36), int(height * 0.87)),
        (max(3, int(width * 0.60)), max(3, int(height * 0.42))),
        0,
        0,
        360,
        cv2.GC_PR_FGD,
        -1,
    )
    cv2.ellipse(
        segmentation,
        (int(width * 0.34), int(height * 0.24)),
        (max(3, int(width * 0.10)), max(3, int(height * 0.09))),
        0,
        0,
        360,
        cv2.GC_FGD,
        -1,
    )
    cv2.ellipse(
        segmentation,
        (int(width * 0.44), int(height * 0.41)),
        (max(3, int(width * 0.10)), max(3, int(height * 0.16))),
        0,
        0,
        360,
        cv2.GC_FGD,
        -1,
    )
    cv2.ellipse(
        segmentation,
        (int(width * 0.52), int(height * 0.51)),
        (max(3, int(width * 0.06)), max(3, int(height * 0.09))),
        0,
        0,
        360,
        cv2.GC_FGD,
        -1,
    )
    cv2.ellipse(
        segmentation,
        (int(width * 0.30), int(height * 0.88)),
        (max(3, int(width * 0.28)), max(3, int(height * 0.22))),
        0,
        0,
        360,
        cv2.GC_FGD,
        -1,
    )
    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        rgb,
        segmentation,
        None,
        background_model,
        foreground_model,
        7,
        cv2.GC_INIT_WITH_MASK,
    )
    mask = np.where(
        (segmentation == cv2.GC_FGD) | (segmentation == cv2.GC_PR_FGD),
        1.0,
        0.0,
    ).astype(np.float32)

    # Keep only a generous head-and-torso region while allowing GrabCut to
    # determine the true subject edge. The guard must never trace the jaw:
    # doing so can remove valid chin pixels when the source or crop shifts.
    subject_guard = np.zeros((height, width), dtype=np.float32)
    cv2.ellipse(
        subject_guard,
        (int(width * 0.39), int(height * 0.37)),
        (max(3, int(width * 0.31)), max(3, int(height * 0.35))),
        0,
        0,
        360,
        1.0,
        -1,
    )
    cv2.ellipse(
        subject_guard,
        (int(width * 0.35), int(height * 0.88)),
        (max(3, int(width * 0.70)), max(3, int(height * 0.50))),
        0,
        0,
        360,
        1.0,
        -1,
    )
    subject_guard = cv2.GaussianBlur(subject_guard, (0, 0), sigmaX=1.6)
    mask *= subject_guard

    # Fail safely to the old soft portrait window if segmentation ever returns
    # an implausibly small or broad region after a source-photo change.
    coverage = float(mask.mean())
    if not 0.24 <= coverage <= 0.82:
        yy, xx = np.ogrid[:height, :width]
        distance = (
            ((xx - width * 0.42) / max(1.0, width * 0.68)) ** 2
            + ((yy - height * 0.58) / max(1.0, height * 0.74)) ** 2
        )
        mask = np.clip((1.13 - distance) / 0.33, 0.0, 1.0).astype(np.float32)
        mask *= subject_guard
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, width / 180))

    prepared = gray.astype(np.float32) * mask + 255.0 * (1.0 - mask)
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
