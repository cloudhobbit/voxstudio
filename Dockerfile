# Vox Studio in a container (CPU). The model and your workspace live in the /data volume.
#   docker run --rm -p 7860:7860 -v voxstudio:/data ghcr.io/cloudhobbit/voxstudio
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg espeak-ng \
 && rm -rf /var/lib/apt/lists/*

# CPU-only torch first: the default Linux wheel carries GPU libraries several times its size.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home vox && mkdir -p /data && chown vox /data
USER vox
ENV HF_HOME=/data/models
VOLUME /data
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=3)"

# 0.0.0.0 is the container's own interface; publish the port to localhost only if others share your network:
#   -p 127.0.0.1:7860:7860
ENTRYPOINT ["voxstudio"]
CMD ["serve", "--host", "0.0.0.0", "--workspace", "/data/workspace"]
