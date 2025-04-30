# Build stage
FROM python:3.11.11-slim-bookworm as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libgdal-dev \
    gdal-bin \
    python3-gdal

RUN pip install uv
RUN uv pip install teehr --system
RUN python -m teehr.utils.install_spark_jars

# Runtime stage
FROM python:3.11.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    openjdk-17-jdk \
    procps

RUN if [ "$(dpkg --print-architecture)" = "arm64" ]; then \
        export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-arm64; \
    else \
        export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64; \
    fi

ENV JAVA_HOME=$JAVA_HOME
ENV PATH=$PATH:$JAVA_HOME/bin
ENV GDAL_CONFIG=/usr/bin/gdal-config

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app /app

COPY scripts/ .
COPY run_controller.sh launch/run_controller.sh
RUN chmod +x /app/launch/run_controller.sh

# Install JupyterLab
RUN pip install --no-cache-dir jupyterlab

# Expose the port that JupyterLab uses
EXPOSE 8888

ENTRYPOINT ["/app/launch/run_controller.sh"]
