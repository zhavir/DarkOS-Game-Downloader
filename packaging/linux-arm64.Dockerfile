# syntax=docker/dockerfile:1
ARG BUILDER_IMAGE=ubuntu:18.04
FROM ${BUILDER_IMAGE} AS builder

RUN apt-get update && \
    apt-get install --yes --no-install-recommends binutils ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ARG PYTHON_ARCHIVE_NAME
COPY .build-cache/${PYTHON_ARCHIVE_NAME} /tmp/python.tar.gz
RUN tar -xzf /tmp/python.tar.gz -C /opt && rm /tmp/python.tar.gz

ENV PATH="/opt/python/bin:${PATH}"
WORKDIR /work

ARG APP_VERSION
ARG APPLICATION_DIRECTORY
ARG EXECUTABLE_NAME
COPY dist/*.whl /tmp/dist/
RUN test -n "$APP_VERSION" && \
    test -n "$APPLICATION_DIRECTORY" && \
    test -n "$EXECUTABLE_NAME" && \
    python3 -m ensurepip --upgrade && \
    python3 -m pip install --no-cache-dir \
        "pyinstaller==6.21.0" \
        "/tmp/dist/pocket_harbor-${APP_VERSION}-py3-none-any.whl"

COPY packaging/frozen_entry.py /work/packaging/frozen_entry.py

RUN python3 -m PyInstaller \
    --clean \
    --noconfirm \
    --onedir \
    --name "$EXECUTABLE_NAME" \
    --copy-metadata pocket-harbor \
    /work/packaging/frozen_entry.py && \
    "/work/dist/$EXECUTABLE_NAME/$EXECUTABLE_NAME" --version && \
    if [ "$EXECUTABLE_NAME" != "$APPLICATION_DIRECTORY" ]; then \
        mv "/work/dist/$EXECUTABLE_NAME" "/work/dist/$APPLICATION_DIRECTORY"; \
    fi

FROM scratch AS export
ARG APPLICATION_DIRECTORY
COPY --from=builder /work/dist/${APPLICATION_DIRECTORY} /${APPLICATION_DIRECTORY}
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /ca-certificates.crt
