"""BoardLocator: find the four ArUco markers of the printed mat and warp the board to a top-down view.

With 4 markers the inner corners give the homography to 1024×768. With 3, the 4th inner corner is inferred from a
homography fitted to all 12 detected marker corners (exact for a flat mat under perspective), falling back to
parallelogram completion if that fit fails. Otherwise the board is "not found". When markers are disabled
(MARKERS_ENABLED=false) a configurable fixed ROI is used instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

from polarity.demo import geometry as g

TEAL_BGR = (191, 212, 45)   # #2DD4BF
AMBER_BGR = (11, 158, 245)  # #F59E0B

# For marker id at mat position k (0=TL, 1=TR, 2=BR, 3=BL), the index of its corner closest to the mat centre.
# ArUco returns corners clockwise from the marker's own top-left: TL, TR, BR, BL.
_INNER_CORNER_INDEX = (2, 3, 0, 1)
# Top-left of each printed marker in mat millimetres (origin = mat inner top-left corner).
_MARKER_ORIGIN_MM = ((-g.MARKER_MM, -g.MARKER_MM), (g.MAT_W_MM, -g.MARKER_MM), (g.MAT_W_MM, g.MAT_H_MM),
                     (-g.MARKER_MM, g.MAT_H_MM))
_INNER_MM = ((0.0, 0.0), (g.MAT_W_MM, 0.0), (g.MAT_W_MM, g.MAT_H_MM), (0.0, g.MAT_H_MM))


def _marker_corners_mm(pos: int) -> list[tuple[float, float]]:
    x, y = _MARKER_ORIGIN_MM[pos]
    m = g.MARKER_MM
    return [(x, y), (x + m, y), (x + m, y + m), (x, y + m)]  # ArUco order: TL, TR, BR, BL


@dataclass
class BoardDetection:
    found: bool
    markers_found: int
    ids: list[int] = field(default_factory=list)
    quad: np.ndarray | None = None          # 4×2 float32 inner corners in frame coords: TL, TR, BR, BL
    inferred: bool = False                  # True when the 4th corner was completed from 3 markers
    mode: Literal["markers", "roi"] = "markers"
    marker_corners: list[np.ndarray] = field(default_factory=list)


class BoardLocator:
    def __init__(self, warp_size: tuple[int, int] = (1024, 768), marker_ids: tuple[int, ...] = (0, 1, 2, 3),
                 markers_enabled: bool = True, roi: tuple[float, float, float, float] = (0.15, 0.10, 0.70, 0.80)) -> None:
        self.warp_w, self.warp_h = warp_size
        self.marker_ids = tuple(marker_ids)
        self.markers_enabled = markers_enabled
        self.roi = roi
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(dictionary, params)

    @classmethod
    def from_config(cls, config: object) -> BoardLocator:
        b = config.settings.board  # type: ignore[attr-defined]
        return cls((b.warp_width, b.warp_height), tuple(b.marker_ids), config.env.markers_enabled,  # type: ignore[attr-defined]
                   tuple(b.roi))

    def detect(self, frame: np.ndarray) -> BoardDetection:
        """Locate the board in a BGR frame."""
        h, w = frame.shape[:2]
        if not self.markers_enabled:
            x, y, rw, rh = self.roi
            quad = np.array([[x * w, y * h], [(x + rw) * w, y * h], [(x + rw) * w, (y + rh) * h],
                             [x * w, (y + rh) * h]], dtype=np.float32)
            return BoardDetection(found=True, markers_found=0, quad=quad, mode="roi")
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = 1.0
        if w > 1920:  # keep detection fast on 4K webcams
            scale = 1920.0 / w
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        corners, ids, _ = self._detector.detectMarkers(gray)
        inner: dict[int, np.ndarray] = {}
        by_pos: dict[int, np.ndarray] = {}
        found_ids: list[int] = []
        marker_corners: list[np.ndarray] = []
        if ids is not None:
            for c, mid in zip(corners, ids.flatten().tolist(), strict=False):
                if mid in self.marker_ids and mid not in found_ids:
                    pos = self.marker_ids.index(mid)
                    pts = (c.reshape(4, 2) / scale).astype(np.float32)
                    inner[pos] = pts[_INNER_CORNER_INDEX[pos]]
                    by_pos[pos] = pts
                    found_ids.append(mid)
                    marker_corners.append(pts)
        n = len(inner)
        if n < 3:
            return BoardDetection(found=False, markers_found=n, ids=found_ids, marker_corners=marker_corners)
        inferred = False
        if n == 3:
            missing = next(k for k in range(4) if k not in inner)
            inner[missing] = self._infer_corner(by_pos, missing)
            inferred = True
        quad = np.stack([inner[k] for k in range(4)]).astype(np.float32)
        return BoardDetection(found=True, markers_found=n, ids=found_ids, quad=quad, inferred=inferred,
                              marker_corners=marker_corners)

    @staticmethod
    def _infer_corner(by_pos: dict[int, np.ndarray], missing: int) -> np.ndarray:
        """Missing inner corner from a mat→frame homography over all 12 known marker corners; parallelogram
        completion (prev + next − opposite) if the fit is degenerate."""
        src = np.array([pt for pos in sorted(by_pos) for pt in _marker_corners_mm(pos)], dtype=np.float32)
        dst = np.concatenate([by_pos[pos] for pos in sorted(by_pos)]).astype(np.float32)
        hmat, _ = cv2.findHomography(src, dst, 0)
        if hmat is not None and np.isfinite(hmat).all():
            pt = cv2.perspectiveTransform(np.array([[_INNER_MM[missing]]], dtype=np.float32), hmat)
            return pt.reshape(2).astype(np.float32)
        inner = {pos: pts[_INNER_CORNER_INDEX[pos]] for pos, pts in by_pos.items()}
        prev_k, next_k, opp_k = (missing - 1) % 4, (missing + 1) % 4, (missing + 2) % 4
        return (inner[prev_k] + inner[next_k] - inner[opp_k]).astype(np.float32)

    def homography(self, det: BoardDetection, scale: float = 1.0) -> np.ndarray | None:
        if not det.found or det.quad is None:
            return None
        w, h = self.warp_w * scale, self.warp_h * scale
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        return cv2.getPerspectiveTransform(det.quad, dst)

    def warp(self, frame: np.ndarray, det: BoardDetection, scale: float = 1.0) -> np.ndarray | None:
        """Top-down view of the board (``warp_size`` × ``scale``), or ``None`` when the board is not found."""
        hmat = self.homography(det, scale)
        if hmat is None:
            return None
        size = (int(round(self.warp_w * scale)), int(round(self.warp_h * scale)))
        return cv2.warpPerspective(frame, hmat, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def zoom_crop(self, frame: np.ndarray, det: BoardDetection, centre: tuple[float, float],
                  zoom: float = 1.6) -> np.ndarray | None:
        """A ``zoom``× closer view around ``centre`` (fractions of the warped board), re-warped from the full-resolution
        frame so the second look gets genuinely more pixels, not an upscaled copy."""
        big = self.warp(frame, det, scale=zoom)
        if big is None:
            return None
        bh, bw = big.shape[:2]
        cx = min(max(centre[0], 0.0), 1.0) * bw
        cy = min(max(centre[1], 0.0), 1.0) * bh
        x0 = int(round(min(max(cx - self.warp_w / 2, 0), bw - self.warp_w)))
        y0 = int(round(min(max(cy - self.warp_h / 2, 0), bh - self.warp_h)))
        return big[y0 : y0 + self.warp_h, x0 : x0 + self.warp_w].copy()

    def draw_overlay(self, frame: np.ndarray, det: BoardDetection) -> np.ndarray:
        """Copy of ``frame`` with the board quad (teal; amber when inferred) and marker outlines drawn."""
        out = frame.copy()
        thickness = max(2, frame.shape[1] // 480)
        for pts in det.marker_corners:
            cv2.polylines(out, [pts.astype(np.int32)], True, (200, 200, 200), max(1, thickness // 2), cv2.LINE_AA)
        if det.found and det.quad is not None:
            colour = AMBER_BGR if det.inferred else TEAL_BGR
            cv2.polylines(out, [det.quad.astype(np.int32)], True, colour, thickness, cv2.LINE_AA)
        return out
