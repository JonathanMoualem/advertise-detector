FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

WORKDIR /app

RUN pip install --no-cache-dir numpy==1.26.4 transformers==4.41.2 Flask Pillow twilio matplotlib

# --- Bake the CLIP weights into the image so the container needs no network at runtime ---
# CLIP_MODEL_ID must match `clip.model_id` in Server/config.json (rebuild if you change it).
ENV HF_HOME=/opt/hf-cache
ARG CLIP_MODEL_ID=openai/clip-vit-base-patch32
RUN python -c "from transformers import CLIPModel, CLIPProcessor; mid='${CLIP_MODEL_ID}'; CLIPModel.from_pretrained(mid); CLIPProcessor.from_pretrained(mid)"

# Serve the baked-in cache offline — no Hub calls (and faster startup) at runtime.
ENV TRANSFORMERS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

COPY Server/ .

EXPOSE 6000

CMD ["python", "server.py"]
