"""CLIP-based chart type classification and embedding."""
from __future__ import annotations

import base64
import io
import logging

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import CLIPModel, CLIPProcessor
    _clip_available = True
except ImportError:
    _clip_available = False
    logger.warning("CLIP not available — chart parsing disabled")

MODEL_ID = "openai/clip-vit-base-patch32"

CHART_LABELS = [
    "a bar chart",
    "a line chart",
    "a pie chart",
    "a scatter plot",
    "a table with numbers",
    "a text paragraph",
    "a financial graph",
    "a histogram",
]


class ChartParser:
    """Classify chart type and extract CLIP embedding from page images."""

    def __init__(self) -> None:
        self._model = None
        self._processor = None
        if _clip_available:
            try:
                self._processor = CLIPProcessor.from_pretrained(MODEL_ID)
                self._model = CLIPModel.from_pretrained(MODEL_ID)
                self._model.train(False)
                logger.info("CLIP chart parser loaded")
            except Exception as exc:
                logger.warning("Failed to load CLIP model: %s", exc)

    def classify(self, image_b64: str) -> dict:
        """
        Classify chart type from base64-encoded image.

        Returns:
            {
                "chart_type": str,
                "confidence": float,
                "embedding": list[float],   # 512-dim CLIP visual embedding
                "all_scores": dict[str, float],
            }
        """
        if not self._model:
            return {"chart_type": "unknown", "confidence": 0.0, "embedding": [], "all_scores": {}}

        img_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        inputs = self._processor(
            text=CHART_LABELS,
            images=image,
            return_tensors="pt",
            padding=True,
        )

        with torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits_per_image[0]
            probs = logits.softmax(dim=0).tolist()
            image_embedding = outputs.image_embeds[0].tolist()

        best_idx = int(np.argmax(probs))
        all_scores = {CHART_LABELS[i]: round(probs[i], 4) for i in range(len(CHART_LABELS))}

        return {
            "chart_type": CHART_LABELS[best_idx].replace("a ", "").replace("an ", ""),
            "confidence": round(probs[best_idx], 4),
            "embedding": image_embedding,
            "all_scores": all_scores,
        }
