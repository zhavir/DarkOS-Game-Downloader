#!/bin/sh
# Replace and rebuild the uv distributions and self-contained dArkOS R36S bundle.
set -eu

PROJECT_DIR=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
CONFIGURED_VERSION=$(
    sed -n 's/^version = "\([^"]*\)"/\1/p' "$PROJECT_DIR/pyproject.toml" | head -n 1
)
RELEASE_VERSION=${NEW_VERSION:-$CONFIGURED_VERSION}

if [ -z "$CONFIGURED_VERSION" ]; then
    printf '%s\n' "Could not read the project version from pyproject.toml." >&2
    exit 1
fi
if [ "$CONFIGURED_VERSION" != "$RELEASE_VERSION" ]; then
    printf '%s\n' \
        "Semantic release requested $RELEASE_VERSION but pyproject.toml contains $CONFIGURED_VERSION." \
        >&2
    exit 1
fi

CACHE_DIR="$PROJECT_DIR/.build-cache"
PYTHON_ARCHIVE="$CACHE_DIR/cpython-3.14.6-aarch64-linux-gnu.tar.gz"
PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20260718/cpython-3.14.6%2B20260718-aarch64-unknown-linux-gnu-install_only_stripped.tar.gz"
BUNDLE="$PROJECT_DIR/dist/darkos-downloader-$RELEASE_VERSION-r36s-arm64.zip"
WHEEL="$PROJECT_DIR/dist/darkos_downloader-$RELEASE_VERSION-py3-none-any.whl"
SDIST="$PROJECT_DIR/dist/darkos_downloader-$RELEASE_VERSION.tar.gz"
WORK_DIR=$(mktemp -d /tmp/darkos-downloader-arm64.XXXXXX)

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$CACHE_DIR" "$PROJECT_DIR/dist"
rm -f "$BUNDLE" "$WHEEL" "$SDIST"

cd "$PROJECT_DIR"
uv lock
uv build

printf '%s\n' "Downloading a fresh ARM64 Python build..."
if command -v curl >/dev/null 2>&1; then
    curl -L --fail --show-error "$PYTHON_URL" -o "$PYTHON_ARCHIVE"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$PYTHON_ARCHIVE" "$PYTHON_URL"
else
    printf '%s\n' "curl or wget is required." >&2
    exit 1
fi

if ! docker run --rm --platform linux/arm64 ubuntu:18.04 /bin/true >/dev/null 2>&1; then
    printf '%s\n' "Registering Docker's ARM64 emulation support..."
    docker run --privileged --rm tonistiigi/binfmt --install arm64
fi

printf '%s\n' "Building the dArkOS Linux ARM64 executable..."
docker build \
    --no-cache \
    --platform linux/arm64 \
    --build-arg "APP_VERSION=$RELEASE_VERSION" \
    --file "$PROJECT_DIR/packaging/darkos-r36s-arm64.Dockerfile" \
    --output "type=local,dest=$WORK_DIR/export" \
    "$PROJECT_DIR"

EXECUTABLE="$WORK_DIR/export/darkos-downloader/darkos-downloader"
if ! file "$EXECUTABLE" | grep -q "ARM aarch64"; then
    printf '%s\n' "The generated executable is not Linux ARM64." >&2
    file "$EXECUTABLE" >&2
    exit 1
fi

mkdir -p "$WORK_DIR/bundle/tools/darkos-downloader"
cp -R "$WORK_DIR/export/darkos-downloader/." "$WORK_DIR/bundle/tools/darkos-downloader/"
cp "$WORK_DIR/export/ca-certificates.crt" \
    "$WORK_DIR/bundle/tools/darkos-downloader/ca-certificates.crt"
cp "$PROJECT_DIR/darkos/dArkOS Downloader.sh" "$WORK_DIR/bundle/tools/dArkOS Downloader.sh"
chmod +x \
    "$WORK_DIR/bundle/tools/dArkOS Downloader.sh" \
    "$WORK_DIR/bundle/tools/darkos-downloader/darkos-downloader"

(cd "$WORK_DIR/bundle" && zip -qr "$BUNDLE" tools)

if [ ! -f "$WHEEL" ] || [ ! -f "$SDIST" ] || [ ! -f "$BUNDLE" ]; then
    printf '%s\n' "One or more expected release artifacts were not created." >&2
    exit 1
fi

printf '%s\n' "Release artifacts created in $PROJECT_DIR/dist"
file "$EXECUTABLE"
