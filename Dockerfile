# Build stage
FROM python:3.11.11-slim-bookworm as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    libgdal-dev \
    gdal-bin \
    python3-gdal

COPY requirements.txt .
RUN pip install uv
RUN uv pip install --no-cache-dir -r requirements.txt --system

# Runtime stage
FROM python:3.11.11-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    openjdk-17-jdk

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
COPY interactive_session.sh launch/interactive_session.sh
RUN chmod +x /app/launch/interactive_session.sh

# Install JupyterLab and any other dependencies
RUN pip install --no-cache-dir jupyterlab

# Expose the port that JupyterLab uses
EXPOSE 8888

ENTRYPOINT ["/app/launch/interactive_session.sh"]
