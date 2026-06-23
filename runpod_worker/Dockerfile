FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/runpod-volume/hf-cache \
    TRANSFORMERS_CACHE=/runpod-volume/hf-cache \
    WHISPERX_CACHE=/runpod-volume/whisperx-cache

WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY runpod_worker/requirements.txt /worker/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 \
    && python3 -m pip install --no-cache-dir -r /worker/requirements.txt

COPY runpod_worker/handler.py /worker/handler.py

CMD ["python3", "-u", "handler.py"]
