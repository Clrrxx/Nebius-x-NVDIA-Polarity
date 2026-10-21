"""LedDetector: on-device physical ground truth for the power-on test.

Compares the warped frame with a warped baseline taken at step start (LED off):
candidate = (V − V_baseline ≥ v_delta_min) AND [(hue in the LED colour's range AND S ≥ s_min)
            OR (V ≥ core_v_min next to a coloured halo: an over-exposed white core)],
then a morphological open and connected components filtered by area. Skin-coloured pixels are excluded
(``led.skin_reject``) because the power test asks the student to hold the button with a finger.

``signal_strength`` (0–1) says how strong the physical evidence is for the reported ``lit`` value:
- lit: blob size and brightness rise of the best blob;
- not lit: 1 − the best sub-threshold "near miss" score, capped low when there is no baseline, when the baseline
  looks like it already contains a lit LED, or when the LED looks covered (so neither can fake strong "off").
Without a baseline only an over-exposed core with a coloured halo counts, and absolute evidence is never "strong".
"""

from __future__ import annotations

import cv2
import numpy as np

from polarity.models.verdict import LedResult

_HUES = {
    "green": [(40, 85)],
    "yellow": [(18, 35)],
    "blue": [(95, 130)],
}


def skin_mask(hsv: np.ndarray) -> np.ndarray:
    """Classic YCrCb skin band (Cr 133–173, Cb 77–127). A fingertip holding the button is "reddish" in HSV;
    a glowing red LED is not in this band (its Cr is far higher), so this keeps hands from looking like light."""
    ycrcb = cv2.cvtColor(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR), cv2.COLOR_BGR2YCrCb)
    y, cr, cb = ycrcb[..., 0], ycrcb[..., 1], ycrcb[..., 2]
    return (cr >= 133) & (cr <= 173) & (cb >= 77) & (cb <= 127) & (y > 60)


class LedDetector:
    def __init__(self, settings: object) -> None:
        self.s = settings

    def _hue_ranges(self, colour: str) -> list[tuple[int, int]]:
        if colour == "red":
            return [tuple(r) for r in self.s.red_hue_ranges]  # type: ignore[attr-defined]
        return _HUES.get(colour, [])

    def _colour_mask(self, hsv: np.ndarray, colour: str) -> np.ndarray:
        h, s = hsv[..., 0], hsv[..., 1]
        if colour == "white":
            return (s < 60) & (hsv[..., 2] >= 200)
        mask = np.zeros(h.shape, dtype=bool)
        for lo, hi in self._hue_ranges(colour):
            mask |= (h >= lo) & (h <= hi)
        mask &= s >= self.s.s_min  # type: ignore[attr-defined]
        if getattr(self.s, "skin_reject", True):
            mask &= ~skin_mask(hsv)
        return mask

    @staticmethod
    def _components(mask: np.ndarray, min_area: float, max_area: float,
                    delta: np.ndarray | None) -> list[dict[str, float]]:
        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
        blobs = []
        for i in range(1, n):
            area = float(stats[i, cv2.CC_STAT_AREA])
            if area < min_area or area > max_area:
                continue
            bw, bh = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
            if max(bw, bh) / max(1, min(bw, bh)) > 3.0:  # LED glow is roundish; wires and rail lines are not
                continue
            region = labels == i
            mean_dv = float(delta[region].mean()) if delta is not None else 0.0
            blobs.append({"x": int(stats[i, cv2.CC_STAT_LEFT]), "y": int(stats[i, cv2.CC_STAT_TOP]),
                          "w": int(stats[i, cv2.CC_STAT_WIDTH]), "h": int(stats[i, cv2.CC_STAT_HEIGHT]),
                          "area": area, "cx": float(cents[i][0]), "cy": float(cents[i][1]), "mean_dv": mean_dv})
        return blobs

    def _score(self, blob: dict[str, float]) -> float:
        min_area = float(self.s.min_area_px)  # type: ignore[attr-defined]
        return 0.5 * min(1.0, blob["area"] / (4 * min_area)) + 0.5 * min(1.0, blob["mean_dv"] / 120.0)

    def mask(self, warped: np.ndarray, baseline: np.ndarray | None, colour: str = "red") -> np.ndarray:
        """Binary candidate mask (uint8 0/255) for the debug view."""
        cand, _, _ = self._candidates(warped, baseline, colour, relaxed=False)
        return (cand * 255).astype(np.uint8)

    def _candidates(self, warped: np.ndarray, baseline: np.ndarray | None, colour: str,
                    relaxed: bool) -> tuple[np.ndarray, np.ndarray | None, np.ndarray]:
        s = self.s
        hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)
        v = hsv[..., 2].astype(np.int16)
        col = self._colour_mask(hsv, colour)
        dv_min = float(s.v_delta_min) * (0.5 if relaxed else 1.0)  # type: ignore[attr-defined]
        delta = None
        if baseline is not None and baseline.shape == warped.shape:
            base_v = cv2.cvtColor(baseline, cv2.COLOR_BGR2HSV)[..., 2].astype(np.int16)
            delta = (v - base_v).astype(np.float32)
            rise = delta >= dv_min
            halo = cv2.dilate((col & (delta >= dv_min / 2)).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        else:  # no baseline: only an over-exposed core with a coloured halo counts (red wires never glow)
            halo = cv2.dilate(col.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
            core_only = (v >= int(s.core_v_min)) & halo  # type: ignore[attr-defined]
            core_only = cv2.morphologyEx(core_only.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
            return core_only, None, col
        core = (v >= int(s.core_v_min)) & halo  # type: ignore[attr-defined]
        cand = rise & (col | core)
        cand = cv2.morphologyEx(cand.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        return cand, delta, col

    def detect(self, warped: np.ndarray, baseline: np.ndarray | None, colour: str = "red") -> LedResult:
        s = self.s
        min_area, max_area = float(s.min_area_px), float(s.max_area_px)  # type: ignore[attr-defined]
        cand, delta, col = self._candidates(warped, baseline, colour, relaxed=False)
        blobs = self._components(cand, min_area, max_area, delta)
        has_baseline = delta is not None
        if not has_baseline:
            blobs = [b for b in blobs if self._bright_halo(warped, col, b, colour)]
        if blobs:
            best = max(self._score(b) for b in blobs)
            strength = best if has_baseline else min(best, 0.45)  # absolute-only evidence is never "strong"
            blobs.sort(key=lambda b: -b["area"])
            return LedResult(lit=True, signal_strength=round(float(strength), 3), blobs=blobs[:5],
                             baseline_used=has_baseline,
                             note=None if has_baseline else "No baseline frame; absolute colour detection only.")
        if not has_baseline:
            return LedResult(lit=False, signal_strength=0.4, blobs=[], baseline_used=False,
                             note="No baseline frame; cannot strongly confirm the LED is off.")
        relaxed, _, _ = self._candidates(warped, baseline, colour, relaxed=True)
        near = self._components(relaxed, min_area / 3, max_area, delta)
        partial = max((self._score(b) for b in near), default=0.0)
        strength = 1.0 - partial
        note = None
        hsv = cv2.cvtColor(warped, cv2.COLOR_BGR2HSV)
        # A large, very bright, strongly saturated blob that did NOT rise above the baseline means the baseline
        # may already show the LED lit (taken at the wrong moment): never strong evidence of "off".
        absolute = col & (hsv[..., 2] >= 235) & (hsv[..., 1] >= 120)
        if self._components(absolute, 2 * min_area, max_area, None):
            strength = min(strength, 0.3)
            note = "A bright LED-coloured spot matches the baseline; the baseline may already show the LED lit."
        elif self._led_occluded(hsv, baseline, colour):
            strength = min(strength, 0.3)
            note = "Something covers the LED compared with the baseline; cannot confirm it is off."
        return LedResult(lit=False, signal_strength=round(float(max(0.0, min(1.0, strength))), 3), blobs=[],
                         baseline_used=True, note=note)

    @staticmethod
    def _bright_halo(warped: np.ndarray, col: np.ndarray, blob: dict[str, float], colour: str) -> bool:
        """A glowing LED's core sits inside a bright, coloured halo; a glint on an unlit LED sits on a darker body."""
        h, w = col.shape
        r = int(max(blob["w"], blob["h"]) / 2 + 4)
        cx, cy = int(blob["cx"]), int(blob["cy"])
        yy, xx = np.ogrid[:h, :w]
        d2 = (xx - cx) ** 2 + (yy - cy) ** 2
        ring = (d2 > r * r) & (d2 <= (2 * r + 4) ** 2)
        if not ring.any():
            return False
        px = warped[ring].astype(np.float32)  # BGR
        bright = float(px.max(axis=1).mean()) >= 190
        if colour == "red":
            return bright and float((px[:, 2] - np.maximum(px[:, 0], px[:, 1])).mean()) >= 25
        return bright and float(col[ring].mean()) >= 0.4

    def _led_occluded(self, hsv: np.ndarray, baseline: np.ndarray, colour: str) -> bool:
        """True if a compact, LED-sized coloured blob in the baseline has mostly lost its colour now
        (e.g. a finger over the LED). Elongated shapes such as rail lines and wires are ignored."""
        base_hsv = cv2.cvtColor(baseline, cv2.COLOR_BGR2HSV)
        base_col = self._colour_mask(base_hsv, colour) & (base_hsv[..., 2] >= 60)
        now_col = self._colour_mask(hsv, colour)
        n, labels, stats, _ = cv2.connectedComponentsWithStats(base_col.astype(np.uint8), connectivity=8)
        for i in range(1, n):
            w, h = int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])
            area = float(stats[i, cv2.CC_STAT_AREA])
            if area < 4 * float(self.s.min_area_px) or area > float(self.s.max_area_px):  # type: ignore[attr-defined]
                continue
            if max(w, h) / max(1, min(w, h)) > 1.8 or area / float(w * h) < 0.5:
                continue
            region = labels == i
            if float(now_col[region].mean()) < 0.5:
                return True
        return False
