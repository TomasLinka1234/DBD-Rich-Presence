"""Čtení textu z výřezu obrazovky (RapidOCR, běží lokálně na CPU, offline)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Line:
    text: str
    score: float
    x0: float  # pixely uvnitř výřezu
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


class Ocr:
    """Tenký obal kolem RapidOCR + krátká cache pro výřezy, které se nemění.

    V menu se obraz skoro nehýbe, takže když vypadá výřez stejně jako minule,
    vrátí se minulý výsledek a OCR se vůbec nespouští (šetří CPU během hry).
    """

    CACHE_MAX_AGE = 8.0      # s
    CACHE_MAX_DIFF = 3.0     # největší průměrný rozdíl jasu v bloku 8x8 zmenšeniny (0-255)

    def __init__(self, threads: int = 2) -> None:
        from rapidocr import RapidOCR

        self.engine = RapidOCR(params={
            "Global.log_level": "error",
            "Global.use_cls": False,  # text ve hře není otočený
            "EngineConfig.onnxruntime.intra_op_num_threads": max(1, int(threads)),
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            # Úzké pruhy se nesmí zvětšovat (výchozí 'min' by je nafoukl 7x).
            "Det.limit_type": "max",
            "Det.limit_side_len": 1600,
        })
        self._cache: dict[str, tuple[np.ndarray, float, list[Line]]] = {}
        self.calls = 0
        self.seconds = 0.0

    @staticmethod
    def _thumb(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        tw = 192
        th = max(8, round(tw * h / max(1, w) / 8) * 8)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, (tw, th), interpolation=cv2.INTER_AREA).astype(np.int16)

    @staticmethod
    def _diff(a: np.ndarray, b: np.ndarray) -> float:
        """Největší změna v jednom bloku 8x8: i malá změna textu (jiné jméno)
        se pozná, i když je zbytek výřezu stejný."""
        d = np.abs(a - b).astype(np.float32)
        h, w = d.shape
        d = d[: h - h % 8, : w - w % 8]
        if d.size == 0:
            return float(np.abs(a - b).mean())
        blocks = d.reshape(d.shape[0] // 8, 8, d.shape[1] // 8, 8).mean(axis=(1, 3))
        return float(blocks.max())

    def read(self, img: np.ndarray, key: str | None = None, now: float | None = None) -> list[Line]:
        if img is None or img.size == 0 or img.shape[0] < 8 or img.shape[1] < 8:
            return []
        now = time.time() if now is None else now
        thumb = None
        if key is not None:
            thumb = self._thumb(img)
            cached = self._cache.get(key)
            if cached is not None:
                old_thumb, when, lines = cached
                if (old_thumb.shape == thumb.shape and now - when <= self.CACHE_MAX_AGE
                        and self._diff(old_thumb, thumb) <= self.CACHE_MAX_DIFF):
                    return lines
        t0 = time.perf_counter()
        # Příznaky vždy výslovně: RapidOCR si je mezi voláními pamatuje (viz rec_only).
        res = self.engine(np.ascontiguousarray(img), use_det=True, use_cls=False, use_rec=True)
        self.seconds += time.perf_counter() - t0
        self.calls += 1
        txts = getattr(res, "txts", None) or ()
        scores = getattr(res, "scores", None) or ()
        boxes = getattr(res, "boxes", None)
        lines: list[Line] = []
        if boxes is not None:
            for txt, sc, box in zip(txts, scores, boxes, strict=False):
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                lines.append(Line(str(txt), float(sc), min(xs), min(ys), max(xs), max(ys)))
        lines.sort(key=lambda ln: (round(ln.y0 / 4), ln.x0))
        if key is not None and thumb is not None:
            self._cache[key] = (thumb, now, lines)
        return lines

    def rec_only(self, img: np.ndarray) -> str:
        """Jen rozpoznání textu (bez hledání), pro malý výřez s jedním slovem/číslem."""
        t0 = time.perf_counter()
        try:
            res = self.engine(np.ascontiguousarray(img), use_det=False, use_cls=False, use_rec=True)
        except Exception:
            return ""
        finally:
            self.seconds += time.perf_counter() - t0
            self.calls += 1
        txts = getattr(res, "txts", None) or ()
        return "".join(str(t) for t in txts)

    def forget(self, key: str | None = None) -> None:
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)
