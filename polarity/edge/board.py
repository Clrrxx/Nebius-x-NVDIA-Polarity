"""BoardLocator: find the four ArUco corner markers and warp the board to a top-down view.

Any arrangement of the four markers works, so hand-placed markers around any breadboard are fine:

- each marker's inner corner is its corner nearest the middle of the markers, so a marker may be turned;
- the inner corners are ordered clockwise starting at marker ``marker_ids[0]``, so the other ids may sit at any
  corner;
- the board's true width : height is measured from the markers themselves. They are squares, and mapping the
  inner quad to a unit square stretches every marker by exactly 1/width × 1/height. A layout within 20 % of the
  warp's own aspect (the printed mat: 120 × 90 mm, ids 0-3 clockwise from top-left, 4:3) fills ``warp_size``
  exactly. Any other layout keeps its true aspect at the same width (a full-size breadboard gives about
  1024 × 350). A portrait layout is turned so its long side is horizontal: by default the view turns 90°
  counter-clockwise, so marker ``marker_ids[0]`` ends bottom-left (``board.portrait_turn: cw`` turns the other
  way, for when the board's printed numbers come out upside down).

With 3 markers the 4th inner corner comes from a homography fitted to all 12 visible marker corners, using the
layout learned from the last 4-marker frame (or the printed mat's layout before any was seen). If neither fits
what the camera sees, the corner completes the rectangle, worked out in each visible marker's own undistorted
frame (markers are squares, so that frame has no perspective). With fewer than 3 markers the board is "not
found". When markers are disabled (MARKERS_ENABLED=false) a configurable fixed ROI is used instead.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import cv2
import numpy as np

from polarity.demo import geometry as g

TEAL_BGR = (191, 212, 45)   # #2DD4BF
AMBER_BGR = (11, 158, 245)  # #F59E0B

# Printed mat: for marker id at mat position k (0=TL, 1=TR, 2=BR, 3=BL), the index of its corner closest to the mat
# centre. ArUco returns corners clockwise from the marker's own top-left: TL, TR, BR, BL.
_INNER_CORNER_INDEX = (2, 3, 0, 1)
# Top-left of each printed marker in mat millimetres (origin = mat inner top-left corner).
_MARKER_ORIGIN_MM = ((-g.MARKER_MM, -g.MARKER_MM), (g.MAT_W_MM, -g.MARKER_MM), (g.MAT_W_MM, g.MAT_H_MM),
                     (-g.MARKER_MM, g.MAT_H_MM))

ASPECT_TOLERANCE = 0.20       # layouts within 20 % of the warp's aspect fill warp_size exactly
PORTRAIT_TURN = 1 / 1.15      # width : height below this is turned so the long side is horizontal
SIZE_KEEP = 0.04              # re-measured aspect within 4 % of the learned one keeps the learned warp size
REFIT_MAX = 0.10              # 3-marker fit to a known layout: max mean corner error, as a fraction of a marker side
_UNIT_SQUARE = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)


def _marker_corners_mm(pos: int) -> list[tuple[float, float]]:
    x, y = _MARKER_ORIGIN_MM[pos]
    m = g.MARKER_MM
    return [(x, y), (x + m, y), (x + m, y + m), (x, y + m)]  # ArUco order: TL, TR, BR, BL


@dataclass
class BoardDetection:
    found: bool
    markers_found: int
    ids: list[int] = field(default_factory=list)
    quad: np.ndarray | None = None          # 4×2 float32 inner corners in frame coords: warp TL, TR, BR, BL
    inferred: bool = False                  # True when the 4th corner was completed from 3 markers
    mode: Literal["markers", "roi"] = "markers"
    marker_corners: list[np.ndarray] = field(default_factory=list)
    size: tuple[int, int] | None = None     # warp (width, height); None means the locator's warp_size
    aspect: float | None = None             # measured width : height of the marker rectangle (after any turn)
    note: str = ""                          # how the board was found, or why not


@dataclass(frozen=True, eq=False)
class _Layout:
    """Where each marker sits relative to the warped board."""

    slots: tuple[int, ...]                  # marker id at warp TL, TR, BR, BL
    inner: dict[int, int]                   # marker id → index of its inner corner (ArUco order)
    corners: dict[int, np.ndarray]          # marker id → its 4 corners in warp pixels (ArUco order)
    size: tuple[int, int]                   # warp (width, height)
    aspect: float                           # true width : height of the inner rectangle


def _aspect(quad: np.ndarray, markers: list[np.ndarray]) -> float | None:
    """True width (TL→TR) : height (TR→BR) of ``quad``, measured from the square markers. Mapping the quad to a unit
    square scales true x by 1/width and y by 1/height, so over a square's four edges Σdx² : Σdy² is
    height² : width², however the square is turned."""
    hmat = cv2.getPerspectiveTransform(quad.astype(np.float32), _UNIT_SQUARE)
    sx = sy = 0.0
    for pts in markers:
        u = cv2.perspectiveTransform(pts.reshape(-1, 1, 2).astype(np.float32), hmat).reshape(-1, 2)
        e = np.roll(u, -1, axis=0) - u
        sx += float((e[:, 0] ** 2).sum())
        sy += float((e[:, 1] ** 2).sum())
    if not (math.isfinite(sx) and math.isfinite(sy) and sx > 0 and sy > 0):
        return None
    return math.sqrt(sy / sx)


def _side(pts: np.ndarray) -> float:
    return float(np.linalg.norm(np.roll(pts, -1, axis=0) - pts, axis=1).mean())


class BoardLocator:
    def __init__(self, warp_size: tuple[int, int] = (1024, 768), marker_ids: tuple[int, ...] = (0, 1, 2, 3),
                 markers_enabled: bool = True, roi: tuple[float, float, float, float] = (0.15, 0.10, 0.70, 0.80),
                 portrait_turn: Literal["ccw", "cw"] = "ccw") -> None:
        self.warp_w, self.warp_h = warp_size
        self.portrait_turn = portrait_turn
        self.marker_ids = tuple(marker_ids)
        if len(self.marker_ids) != 4 or len(set(self.marker_ids)) != 4:
            raise ValueError(f"board.marker_ids needs four different ids, got {list(self.marker_ids)}")
        self.markers_enabled = markers_enabled
        self.roi = roi
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        self._detector = cv2.aruco.ArucoDetector(dictionary, params)
        self._mat = self._mat_layout()
        self._learned: _Layout | None = None  # from the last 4-marker frame; used when one marker is hidden

    @classmethod
    def from_config(cls, config: object) -> BoardLocator:
        b = config.settings.board  # type: ignore[attr-defined]
        return cls((b.warp_width, b.warp_height), tuple(b.marker_ids), config.env.markers_enabled,  # type: ignore[attr-defined]
                   tuple(b.roi), b.portrait_turn)

    def _mat_layout(self) -> _Layout:
        """The printed mat: marker ``marker_ids[k]`` at mat position k, filling ``warp_size``."""
        s = np.array([self.warp_w / g.MAT_W_MM, self.warp_h / g.MAT_H_MM], dtype=np.float32)
        corners = {mid: np.array(_marker_corners_mm(pos), dtype=np.float32) * s for pos, mid in enumerate(self.marker_ids)}
        inner = {mid: _INNER_CORNER_INDEX[pos] for pos, mid in enumerate(self.marker_ids)}
        return _Layout(self.marker_ids, inner, corners, (self.warp_w, self.warp_h), g.MAT_W_MM / g.MAT_H_MM)

    # ── detection ────────────────────────────────────────────────────────────────────────────

    def detect(self, frame: np.ndarray) -> BoardDetection:
        """Locate the board in a BGR frame."""
        h, w = frame.shape[:2]
        if not self.markers_enabled:
            x, y, rw, rh = self.roi
            quad = np.array([[x * w, y * h], [(x + rw) * w, y * h], [(x + rw) * w, (y + rh) * h],
                             [x * w, (y + rh) * h]], dtype=np.float32)
            return BoardDetection(found=True, markers_found=0, quad=quad, mode="roi", size=(self.warp_w, self.warp_h))
        found, others = self._find_markers(frame)
        ids, marker_corners = list(found), list(found.values())
        if len(found) < 3:
            note = f"{len(found)} of 4 corner markers visible"
            if others:  # ArUco squares are there, just not ours: a different print or dictionary
                note += (f"; saw marker ids {others}, but this rig uses ids {list(self.marker_ids)}"
                         " (print assets/print/marker_mat_A4.pdf)")
            return BoardDetection(found=False, markers_found=len(found), ids=ids, marker_corners=marker_corners,
                                  note=note)
        if len(found) == 4:
            made = self._make_layout(found, self._inner_corners(found), reuse=self._learned)
            if made is None:
                return BoardDetection(found=False, markers_found=4, ids=ids, marker_corners=marker_corners,
                                      note="the four markers do not outline a board")
            layout, quad = made
            self._learned = layout
            return BoardDetection(found=True, markers_found=4, ids=ids, quad=quad, marker_corners=marker_corners,
                                  size=layout.size, aspect=layout.aspect, note=self._describe(layout))
        for layout in (self._learned, self._mat):
            quad = self._infer_from_layout(found, layout) if layout is not None else None
            if quad is not None:
                assert layout is not None
                return BoardDetection(found=True, markers_found=3, ids=ids, quad=quad, inferred=True,
                                      marker_corners=marker_corners, size=layout.size, aspect=layout.aspect,
                                      note=self._describe(layout) + "; 4th corner from the known layout")
        made = self._complete(found)
        if made is None:
            return BoardDetection(found=False, markers_found=3, ids=ids, marker_corners=marker_corners,
                                  note="the three markers do not outline a board")
        layout, quad = made
        return BoardDetection(found=True, markers_found=3, ids=ids, quad=quad, inferred=True,
                              marker_corners=marker_corners, size=layout.size, aspect=layout.aspect,
                              note=self._describe(layout) + "; 4th corner estimated from the marker squares")

    def _find_markers(self, frame: np.ndarray) -> tuple[dict[int, np.ndarray], list[int]]:
        """(marker id → its 4 corners (frame coords, ArUco order), first detection of each configured id;
        sorted ids of any other DICT_4X4_50 markers seen)."""
        h, w = frame.shape[:2]
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        scale = 1.0
        if max(w, h) > 1920:  # keep detection fast on 4K webcams and phone photos
            scale = 1920.0 / max(w, h)
            gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        corners, ids, _ = self._detector.detectMarkers(gray)
        found: dict[int, np.ndarray] = {}
        others: set[int] = set()
        if ids is not None:
            for c, mid in zip(corners, ids.flatten().tolist(), strict=False):
                if mid in self.marker_ids and mid not in found:
                    found[int(mid)] = (c.reshape(4, 2) / scale).astype(np.float32)
                elif mid not in self.marker_ids:
                    others.add(int(mid))
        return found, sorted(others)

    @staticmethod
    def _inner_corners(found: dict[int, np.ndarray]) -> dict[int, int]:
        """Marker id → index of its corner nearest the middle of all visible markers (works however it is turned)."""
        middle = np.mean([pts.mean(axis=0) for pts in found.values()], axis=0)
        return {mid: int(np.argmin(np.linalg.norm(pts - middle, axis=1))) for mid, pts in found.items()}

    def _clockwise(self, points: dict[int, np.ndarray]) -> list[int]:
        """Ids of four corner points in clockwise screen order, starting at ``marker_ids[0]``."""
        c = np.mean(list(points.values()), axis=0)
        order = sorted(points, key=lambda k: math.atan2(points[k][1] - c[1], points[k][0] - c[0]))  # y down
        i = order.index(self.marker_ids[0])
        return order[i:] + order[:i]

    def _make_layout(self, found: dict[int, np.ndarray], inner: dict[int, int],
                     extra: dict[int, np.ndarray] | None = None,
                     reuse: _Layout | None = None) -> tuple[_Layout, np.ndarray] | None:
        """Layout and frame quad from the visible markers' inner corners (plus a completed corner in ``extra``)."""
        points = {mid: found[mid][i] for mid, i in inner.items()} | (extra or {})
        order = self._clockwise(points)
        quad = np.stack([points[mid] for mid in order]).astype(np.float32)
        marker_area = float(np.mean([cv2.contourArea(p) for p in found.values()]))
        if not cv2.isContourConvex(quad.reshape(-1, 1, 2)) or cv2.contourArea(quad) < marker_area:
            return None
        aspect = _aspect(quad, list(found.values()))
        if aspect is None:
            return None
        if aspect < PORTRAIT_TURN:  # portrait: turn so the long side is horizontal
            k = 1 if self.portrait_turn == "ccw" else -1  # ccw: the next corner clockwise becomes top-left
            order = order[k:] + order[:k]
            quad = np.roll(quad, -k, axis=0)
            aspect = 1.0 / aspect
        if reuse is not None and reuse.slots == tuple(order) and abs(aspect - reuse.aspect) <= SIZE_KEEP * reuse.aspect:
            size, aspect = reuse.size, reuse.aspect  # same layout: keep the warp size stable between frames
        else:
            size = self._size_for(aspect)
        w, h = size
        hmat = cv2.getPerspectiveTransform(quad, np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32))
        corners = {mid: cv2.perspectiveTransform(p.reshape(-1, 1, 2), hmat).reshape(4, 2) for mid, p in found.items()}
        return _Layout(tuple(order), dict(inner), corners, size, aspect), quad

    def _size_for(self, aspect: float) -> tuple[int, int]:
        """Warp size: ``warp_size`` when the aspect is close to it, otherwise the true aspect at the same width (or
        height), rounded to 8 px."""
        base = self.warp_w / self.warp_h
        if abs(aspect - base) <= ASPECT_TOLERANCE * base:
            return self.warp_w, self.warp_h
        if aspect > base:
            return self.warp_w, max(64, int(round(self.warp_w / aspect / 8)) * 8)
        return max(64, int(round(self.warp_h * aspect / 8)) * 8), self.warp_h

    def _infer_from_layout(self, found: dict[int, np.ndarray], layout: _Layout) -> np.ndarray | None:
        """Frame quad from 3 markers and a known layout: homography over the 12 visible corners, the hidden marker's
        inner corner projected through it. ``None`` if the layout does not fit what the camera sees."""
        if not all(mid in layout.corners for mid in found):
            return None
        ids = sorted(found)
        src = np.concatenate([layout.corners[mid] for mid in ids]).astype(np.float32)
        dst = np.concatenate([found[mid] for mid in ids]).astype(np.float32)
        hmat, _ = cv2.findHomography(src, dst, 0)
        if hmat is None or not np.isfinite(hmat).all():
            return None
        err = float(np.linalg.norm(cv2.perspectiveTransform(src.reshape(-1, 1, 2), hmat).reshape(-1, 2) - dst,
                                   axis=1).mean())
        if err > max(2.0, REFIT_MAX * float(np.mean([_side(p) for p in found.values()]))):
            return None
        w, h = layout.size
        rect = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        quad = np.stack([found[mid][layout.inner[mid]] if mid in found
                         else cv2.perspectiveTransform(rect[k].reshape(1, 1, 2), hmat).reshape(2)
                         for k, mid in enumerate(layout.slots)]).astype(np.float32)
        return quad if cv2.isContourConvex(quad.reshape(-1, 1, 2)) else None

    def _complete(self, found: dict[int, np.ndarray]) -> tuple[_Layout, np.ndarray] | None:
        """No known layout fits 3 markers: the hidden inner corner completes the rectangle opposite the corner with
        the widest angle. Mapping a marker's corners to a unit square removes the perspective (up to scale and
        rotation), so the completion A + C - B is exact in that frame; the estimates from all three markers are
        averaged."""
        inner = self._inner_corners(found)
        pts = {mid: found[mid][i] for mid, i in inner.items()}

        def cos_at(mid: int) -> float:
            a, b = (pts[o] - pts[mid] for o in pts if o != mid)
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

        elbow = min(pts, key=cos_at)  # the widest angle has the smallest cosine
        a, b = (o for o in pts if o != elbow)
        estimates = []
        for corners in found.values():
            to_flat = cv2.getPerspectiveTransform(corners.astype(np.float32), _UNIT_SQUARE)
            flat = {mid: cv2.perspectiveTransform(pt.reshape(1, 1, 2).astype(np.float32), to_flat).reshape(2)
                    for mid, pt in pts.items()}
            d = (flat[a] + flat[b] - flat[elbow]).reshape(1, 1, 2).astype(np.float32)
            est = cv2.perspectiveTransform(d, np.linalg.inv(to_flat)).reshape(2)
            if np.isfinite(est).all():
                estimates.append(est)
        if not estimates:
            return None
        missing = next(mid for mid in self.marker_ids if mid not in found)
        return self._make_layout(found, inner, extra={missing: np.mean(estimates, axis=0).astype(np.float32)})

    def _describe(self, layout: _Layout) -> str:
        if layout.size == (self.warp_w, self.warp_h):
            text = f"board {layout.aspect:.2f}:1 fills the {self.warp_w}×{self.warp_h} warp"
        else:
            text = f"board {layout.aspect:.2f}:1 kept at {layout.size[0]}×{layout.size[1]}"
        return text + (", turned to landscape" if layout.slots[0] != self.marker_ids[0] else "")

    # ── warping ──────────────────────────────────────────────────────────────────────────────

    def warp_size(self, det: BoardDetection) -> tuple[int, int]:
        return det.size or (self.warp_w, self.warp_h)

    def homography(self, det: BoardDetection, scale: float = 1.0) -> np.ndarray | None:
        if not det.found or det.quad is None:
            return None
        w, h = (v * scale for v in self.warp_size(det))
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        return cv2.getPerspectiveTransform(det.quad, dst)

    def warp(self, frame: np.ndarray, det: BoardDetection, scale: float = 1.0) -> np.ndarray | None:
        """Top-down view of the board (``det.size`` × ``scale``), or ``None`` when the board is not found."""
        hmat = self.homography(det, scale)
        if hmat is None:
            return None
        w, h = self.warp_size(det)
        size = (int(round(w * scale)), int(round(h * scale)))
        return cv2.warpPerspective(frame, hmat, size, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def region(self, frame: np.ndarray, det: BoardDetection) -> np.ndarray | None:
        """The board's bounding box in ``frame`` at native resolution (for focus), or ``None`` when not found."""
        if not det.found or det.quad is None:
            return None
        h, w = frame.shape[:2]
        x0, y0 = np.floor(det.quad.min(axis=0)).astype(int)
        x1, y1 = np.ceil(det.quad.max(axis=0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        if x1 - x0 < 16 or y1 - y0 < 16:
            return None
        return frame[y0:y1, x0:x1]

    def zoom_crop(self, frame: np.ndarray, det: BoardDetection, centre: tuple[float, float],
                  zoom: float = 1.6) -> np.ndarray | None:
        """A ``zoom``× closer view around ``centre`` (fractions of the warped board), re-warped from the full-resolution
        frame so the second look gets genuinely more pixels, not an upscaled copy. Same size as the normal warp."""
        big = self.warp(frame, det, scale=zoom)
        if big is None:
            return None
        w, h = self.warp_size(det)
        bh, bw = big.shape[:2]
        cx = min(max(centre[0], 0.0), 1.0) * bw
        cy = min(max(centre[1], 0.0), 1.0) * bh
        x0 = int(round(min(max(cx - w / 2, 0), bw - w)))
        y0 = int(round(min(max(cy - h / 2, 0), bh - h)))
        return big[y0 : y0 + h, x0 : x0 + w].copy()

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
