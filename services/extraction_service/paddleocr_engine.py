"""PaddleOCR-based layout analysis and OCR for scanned/image pages."""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import easyocr
    _ocr_available = True
except ImportError:
    _ocr_available = False
    logger.warning("EasyOCR not available — OCR will be skipped")


class PaddleOCREngine:
    """Wraps EasyOCR for text extraction and layout region detection."""

    def __init__(self) -> None:
        self._ocr = None
        if _ocr_available:
            self._ocr = easyocr.Reader(["en"], gpu=False, verbose=False)

    def extract(self, image_b64: str) -> dict:
        """
        Run OCR on a base64-encoded image.

        Returns:
            {
                "text": str,
                "blocks": [{"bbox": [x0,y0,x1,y1], "text": str, "confidence": float}],
                "word_count": int,
            }
        """
        if not self._ocr:
            return {"text": "", "blocks": [], "word_count": 0}

        img_bytes = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img_np = np.array(img)

        results = self._ocr.readtext(img_np)
        blocks = []
        lines = []

        for (coords, text, confidence) in (results or []):
            xs = [p[0] for p in coords]
            ys = [p[1] for p in coords]
            blocks.append({
                "bbox": [min(xs), min(ys), max(xs), max(ys)],
                "text": text,
                "confidence": round(float(confidence), 4),
            })
            lines.append(text)

        full_text = " ".join(lines)
        return {
            "text": full_text,
            "blocks": blocks,
            "word_count": len(full_text.split()),
        }
