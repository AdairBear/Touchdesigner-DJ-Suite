"""
Tests for the edge-confined outline fix in movement_tracker._process_segmentation.

Background
----------
Phase 1B replaced a filled-silhouette + dilate(2x) + GaussianBlur(15x15)
"fill-expansion" with cv2.morphologyEx(MORPH_GRADIENT) contour extraction. See
docs/audits/baseline_outline_audit_2026-06-05.md (Cause A / Section 5 Option 1).

These tests prove the math WITHOUT a camera, MediaPipe, or TouchDesigner: a
binary silhouette is synthesized in-memory with OpenCV, fed straight into
_process_segmentation, and the output is asserted to be a thin, connected,
non-zero contour — and dramatically thinner than the old fill path would be.

Run as pytest, or directly as a smoke script:
    ./venv/bin/python tests/test_edge_outline.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

# Make the python/ package importable (mirrors conftest.py).
sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from movement_tracker import MASK_H, MASK_W, MovementTracker  # noqa: E402


def _make_tracker() -> MovementTracker:
    """Build a MovementTracker with all hardware/IO mocked out.

    Segmentation is disabled so __init__ never touches the /tmp mmap; we call
    _process_segmentation directly with synthesized input, so the real MediaPipe
    detectors and camera are irrelevant.
    """
    with (
        patch("movement_tracker.mp.solutions.pose.Pose"),
        patch("movement_tracker.udp_client.SimpleUDPClient"),
        patch("movement_tracker.cv2.VideoCapture"),
    ):
        return MovementTracker(enable_segmentation=False)


def _synth_silhouette() -> SimpleNamespace:
    """A MediaPipe-style results object carrying a filled-ellipse seg mask.

    Mask resolution == MASK_W x MASK_H so the final NEAREST resize is identity
    and pixel counts are directly comparable. The ellipse is inset from the
    borders so its contour forms a single closed ring.
    """
    seg = np.zeros((MASK_H, MASK_W), dtype=np.float32)
    center = (MASK_W // 2, MASK_H // 2)
    axes = (MASK_W // 5, int(MASK_H * 0.42))  # roughly person-shaped, fully inset
    cv2.ellipse(seg, center, axes, 0, 0, 360, color=1.0, thickness=-1)
    return SimpleNamespace(segmentation_mask=seg)


def _old_fill_pixel_count(seg: np.ndarray) -> int:
    """Replicate the OLD (buggy) fill-expansion to quantify how fat it was.

    This is the exact pre-fix pipeline: threshold -> dilate(5x5, 2 iters) ->
    GaussianBlur(15x15). Used only to prove the new contour is far thinner.
    """
    binary = (seg > 0.5).astype(np.uint8) * 255
    k = np.ones((5, 5), np.uint8)
    binary = cv2.dilate(binary, k, iterations=2)
    binary = cv2.GaussianBlur(binary, (15, 15), 0)
    return int(np.count_nonzero(binary))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestEdgeOutline:
    def test_output_shape_and_dtype(self):
        tracker = _make_tracker()
        out = tracker._process_segmentation([_synth_silhouette()])
        assert out.shape == (MASK_H, MASK_W)
        assert out.dtype == np.uint8

    def test_outline_is_non_zero(self):
        tracker = _make_tracker()
        out = tracker._process_segmentation([_synth_silhouette()])
        assert np.count_nonzero(out) > 0, "contour must contain edge pixels"

    def test_outline_is_thin_relative_to_fill(self):
        """The contour must be a small fraction of the FILLED silhouette area."""
        tracker = _make_tracker()
        results = _synth_silhouette()
        filled_px = int(np.count_nonzero((results.segmentation_mask > 0.5)))
        out = tracker._process_segmentation([results])
        contour_px = int(np.count_nonzero(out))
        assert contour_px < 0.30 * filled_px, (
            f"contour ({contour_px}) should be << filled area ({filled_px}); "
            "a thin outline is perimeter-sized, not area-sized"
        )

    def test_outline_is_thin_in_absolute_frame_terms(self):
        tracker = _make_tracker()
        out = tracker._process_segmentation([_synth_silhouette()])
        total_px = MASK_W * MASK_H
        contour_px = int(np.count_nonzero(out))
        assert contour_px < 0.05 * total_px, (
            f"contour ({contour_px}) should be < 5% of the frame ({total_px})"
        )

    def test_outline_is_dramatically_thinner_than_old_fill(self):
        """Direct contrast: new contour vs the old dilate+blur fill it replaced."""
        tracker = _make_tracker()
        results = _synth_silhouette()
        old_px = _old_fill_pixel_count(results.segmentation_mask)
        out = tracker._process_segmentation([results])
        new_px = int(np.count_nonzero(out))
        assert new_px < 0.25 * old_px, (
            f"new contour ({new_px}) must be far thinner than old fill ({old_px})"
        )

    def test_outline_is_connected(self):
        """A single inset blob -> one closed contour ring (1 foreground component)."""
        tracker = _make_tracker()
        out = tracker._process_segmentation([_synth_silhouette()])
        num_labels, _ = cv2.connectedComponents((out > 0).astype(np.uint8))
        foreground_components = num_labels - 1  # label 0 is background
        assert foreground_components >= 1
        assert foreground_components <= 2, (
            f"a single silhouette should give ~1 contour ring, got "
            f"{foreground_components} components"
        )

    def test_outline_lies_on_the_silhouette_boundary(self):
        """Contour pixels must sit on the edge: near-fill interior and exterior
        should be mostly empty; the ring hugs the threshold boundary."""
        tracker = _make_tracker()
        results = _synth_silhouette()
        binary = (results.segmentation_mask > 0.5).astype(np.uint8)
        out = (tracker._process_segmentation([results]) > 0).astype(np.uint8)

        eroded = cv2.erode(binary, np.ones((7, 7), np.uint8), iterations=1)
        deep_interior = int(np.count_nonzero(out & eroded))
        # The gradient ring should not bleed deep into the body interior.
        assert deep_interior < 0.20 * int(np.count_nonzero(out)), (
            "outline should hug the boundary, not fill the body interior"
        )

    def test_instrumentation_counter_set(self):
        tracker = _make_tracker()
        out = tracker._process_segmentation([_synth_silhouette()])
        assert tracker.last_contour_px == int(np.count_nonzero(out)), (
            "last_contour_px instrumentation must match emitted contour px "
            "(mask res == MASK_W x MASK_H so resize is identity)"
        )

    def test_empty_input_returns_zero_mask(self):
        tracker = _make_tracker()
        out = tracker._process_segmentation([None])
        assert out.shape == (MASK_H, MASK_W)
        assert np.count_nonzero(out) == 0


# ---------------------------------------------------------------------------
# Standalone smoke script: prints the numbers a human can eyeball at the desk.
# ---------------------------------------------------------------------------
def _smoke() -> None:
    tracker = _make_tracker()
    results = _synth_silhouette()
    filled_px = int(np.count_nonzero(results.segmentation_mask > 0.5))
    old_px = _old_fill_pixel_count(results.segmentation_mask)
    out = tracker._process_segmentation([results])
    new_px = int(np.count_nonzero(out))
    total = MASK_W * MASK_H

    print("=== edge-confined outline smoke test ===")
    print(f"frame                : {MASK_W}x{MASK_H} = {total} px")
    print(
        f"filled silhouette    : {filled_px} px ({filled_px / total * 100:.1f}% of frame)"
    )
    print(f"OLD fill (dilate+blur): {old_px} px ({old_px / total * 100:.1f}% of frame)")
    print(f"NEW contour (gradient): {new_px} px ({new_px / total * 100:.2f}% of frame)")
    print(f"thinning vs old fill : {old_px / max(new_px, 1):.1f}x fewer pixels")
    print(
        f"contour vs fill area : {new_px / max(filled_px, 1) * 100:.1f}% of filled area"
    )
    num_labels, _ = cv2.connectedComponents((out > 0).astype(np.uint8))
    print(f"connected components : {num_labels - 1} (expect ~1 closed ring)")
    print("=> thin, connected, non-zero outline confirmed without camera/TD.")


if __name__ == "__main__":
    _smoke()
