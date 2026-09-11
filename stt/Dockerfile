# Marvin streaming STT: NVIDIA Nemotron 3.5 ASR (nemo-toolkit 3.0.0) on CUDA 12.6 wheels.
# Plain python base: torch's cu126 wheels bundle the CUDA runtime, the host only provides the driver
# (580.x on the g4dn nodes). cu126 wheels target sm_75 (T4) through sm_120.
FROM python:3.12-slim
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/cache/hf \
    NVIDIA_VISIBLE_DEVICES=all NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN apt-get update && apt-get install -y --no-install-recommends libsndfile1 ffmpeg build-essential git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python Cython packaging && \
    uv pip install --python /app/.venv/bin/python \
        --extra-index-url https://download.pytorch.org/whl/cu126 --index-strategy unsafe-best-match \
        "nemo-toolkit[asr,cu12]==3.0.0" "aiohttp>=3.12" numpy
COPY marvin_stt ./marvin_stt
ENV PATH=/app/.venv/bin:$PATH
EXPOSE 8765
CMD ["python", "-m", "marvin_stt"]
