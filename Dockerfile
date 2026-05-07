# Build stage
FROM python:3.12-slim-bookworm AS builder

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
FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev \
    gdal-bin \
    openjdk-17-jdk \
 && rm -rf /var/lib/apt/lists/*

RUN if [ "$(dpkg --print-architecture)" = "arm64" ]; then \
        ln -s /usr/lib/jvm/java-17-openjdk-arm64 /usr/lib/jvm/java-17-openjdk; \
    else \
        ln -s /usr/lib/jvm/java-17-openjdk-amd64 /usr/lib/jvm/java-17-openjdk; \
    fi

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk
ENV PATH=$PATH:/usr/lib/jvm/java-17-openjdk/bin
ENV GDAL_CONFIG=/usr/bin/gdal-config
ENV HOME=/tmp

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /app /app

COPY scripts/ .

# Allow the entrypoint to add a /etc/passwd entry for arbitrary UIDs passed
# via --user $(id -u):$(id -g), which Java/Hadoop require for authentication.
RUN chmod a+w /etc/passwd
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh", "python", "teehr_ngen.py"]
