FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models at build time to avoid cold-start delays
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)" || true
RUN python -c "from transformers import AutoImageProcessor, TableTransformerForObjectDetection; \
    AutoImageProcessor.from_pretrained('microsoft/table-transformer-detection'); \
    TableTransformerForObjectDetection.from_pretrained('microsoft/table-transformer-detection')" || true
RUN python -c "from transformers import CLIPModel, CLIPProcessor; \
    CLIPProcessor.from_pretrained('openai/clip-vit-base-patch32'); \
    CLIPModel.from_pretrained('openai/clip-vit-base-patch32')" || true

COPY . .

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
