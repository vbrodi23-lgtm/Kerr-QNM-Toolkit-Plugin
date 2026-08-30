FROM python:3.12-slim-bookworm

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        libatomic1 \
        libgfortran5 \
        libgmp10 \
        libmpfr6 \
        libopenblas0-pthread \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/kerr-qnm-toolkit
COPY requirements.remote.txt ./
RUN python -m pip install --no-cache-dir -r requirements.remote.txt

COPY . ./
ENV PYTHONPATH=/opt/kerr-qnm-toolkit \
    KERR_QNM_TOOLKIT_RUNTIME=/opt/kerr-qnm-runtime \
    KERR_QNM_WORKSPACE_ROOT=/workspace \
    PYTHONUNBUFFERED=1 \
    PORT=8000
RUN python scripts/prepare_container.py \
    && useradd --create-home --uid 10001 toolkit \
    && mkdir -p /workspace /state \
    && chown -R toolkit:toolkit /workspace /state

USER toolkit
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/healthz', timeout=3).read()"
ENTRYPOINT ["python", "scripts/entrypoint.py"]
