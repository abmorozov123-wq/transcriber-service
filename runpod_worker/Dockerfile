FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/runpod-volume/hf-cache \
    TRANSFORMERS_CACHE=/runpod-volume/hf-cache \
    WHISPERX_CACHE=/runpod-volume/whisperx-cache \
    LD_LIBRARY_PATH=/opt/cudnn8/nvidia/cudnn/lib:/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

WORKDIR /worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY runpod_worker/requirements.txt /worker/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 \
    && python3 -m pip install --no-cache-dir --target /opt/cudnn8 nvidia-cudnn-cu12==8.9.7.29 \
    && python3 -m pip install --no-cache-dir -r /worker/requirements.txt

COPY runpod_worker/handler.py /worker/handler.py

RUN python3 - <<'PY'
from handler import get_diarization_api, patch_torchaudio
from handler import patch_torch_serialization
patch_torchaudio()
import torch
import torchaudio
patch_torch_serialization(torch)
import ctranslate2
import whisperx
from pathlib import Path
assert Path("/opt/cudnn8/nvidia/cudnn/lib/libcudnn_ops_infer.so.8").exists()
get_diarization_api(whisperx)
print("smoke ok", torch.__version__, torchaudio.__version__, ctranslate2.__version__)
PY

CMD ["python3", "-u", "handler.py"]
