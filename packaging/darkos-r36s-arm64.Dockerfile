# syntax=docker/dockerfile:1
FROM ubuntu:18.04 AS builder

RUN apt-get update && \
    apt-get install --yes --no-install-recommends binutils ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY .build-cache/cpython-3.14.6-aarch64-linux-gnu.tar.gz /tmp/python.tar.gz
RUN tar -xzf /tmp/python.tar.gz -C /opt && rm /tmp/python.tar.gz

ENV PATH="/opt/python/bin:${PATH}"
WORKDIR /work

ARG APP_VERSION
COPY dist/*.whl /tmp/dist/
RUN test -n "$APP_VERSION" && \
    python3 -m ensurepip --upgrade && \
    python3 -m pip install --no-cache-dir \
        "pyinstaller==6.21.0" \
        "/tmp/dist/darkos_downloader-${APP_VERSION}-py3-none-any.whl"

COPY packaging/frozen_entry.py /work/packaging/frozen_entry.py

RUN python3 -m PyInstaller \
    --clean \
    --noconfirm \
    --onedir \
    --name darkos-downloader \
    --copy-metadata darkos-downloader \
    /work/packaging/frozen_entry.py && \
    /work/dist/darkos-downloader/darkos-downloader --version

FROM scratch AS export
COPY --from=builder /work/dist/darkos-downloader /darkos-downloader
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /ca-certificates.crt
