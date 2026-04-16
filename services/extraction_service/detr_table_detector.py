"""DETR-based table detection and structure extraction."""
from __future__ import annotations

import base64
import io
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoImageProcessor, TableTransformerForObjectDetection
    _detr_available = True
except ImportError:
    _detr_available = False
    logger.warning("transformers/torch not available — table detection disabled")

MODEL_ID = "microsoft/table-transformer-detection"


class DETRTableDetector:
    """Detect table bounding boxes in page images using Table Transformer."""

    SCORE_THRESHOLD = 0.7

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        if _detr_available:
            try:
                self._processor = AutoImageProcessor.from_pretrained(MODEL_ID)
                self._model = TableTransformerForObjectDetection.from_pretrained(MODEL_ID)
                self._model.train(False)
                logger.info("DETR table detector loaded")
            except Exception as exc:
                logger.warning("Failed to load DETR model: %s", exc)

    def detect(self, image_b64: str) -> list[dict]:
        """
        Detect tables in a base64-encoded page image.

        Returns list of:
            {"bbox": [x0, y0, x1, y1], "score": float, "label": str}
        """
        if not self._model:
            return []

        img_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        inputs = self._processor(images=image, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(**inputs)

        target_sizes = torch.tensor([image.size[::-1]])
        results = self._processor.post_process_object_detection(
            outputs, threshold=self.SCORE_THRESHOLD, target_sizes=target_sizes
        )[0]

        detections = []
        for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
            x0, y0, x1, y1 = box.tolist()
            detections.append({
                "bbox": [round(x0), round(y0), round(x1), round(y1)],
                "score": round(float(score), 4),
                "label": self._model.config.id2label[int(label)],
            })

        return detections
