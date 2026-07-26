#!/bin/sh
# Build Python distributions, one target bundle, or both.
set -eu

PROJECT_DIR=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
BUILD_MODE=all
REQUESTED_TARGET=${POCKET_HARBOR_TARGET:-darkos}
case "${1:-}" in
    --python)
        if [ "$#" -ne 1 ]; then
            printf '%s\n' "Usage: $0 --python" >&2
            exit 2
        fi
        BUILD_MODE=python
        ;;
    --platform)
        if [ "$#" -ne 2 ]; then
            printf '%s\n' "Usage: $0 --platform TARGET" >&2
            exit 2
        fi
        BUILD_MODE=platform
        REQUESTED_TARGET=$2
        ;;
    '')
        ;;
    *)
        if [ "$#" -ne 1 ]; then
            printf '%s\n' "Usage: $0 [TARGET | --python | --platform TARGET]" >&2
            exit 2
        fi
        REQUESTED_TARGET=$1
        ;;
esac

CONFIGURED_VERSION=$(
    sed -n 's/^version = "\([^"]*\)"/\1/p' "$PROJECT_DIR/pyproject.toml" | head -n 1
)
RELEASE_VERSION=${NEW_VERSION:-$CONFIGURED_VERSION}
WHEEL="$PROJECT_DIR/dist/pocket_harbor-$RELEASE_VERSION-py3-none-any.whl"
SDIST="$PROJECT_DIR/dist/pocket_harbor-$RELEASE_VERSION.tar.gz"

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

mkdir -p "$PROJECT_DIR/dist"
cd "$PROJECT_DIR"

if [ "$BUILD_MODE" = python ]; then
    rm -f "$WHEEL" "$SDIST"
    uv lock --check
    uv build
    if [ ! -f "$WHEEL" ] || [ ! -f "$SDIST" ]; then
        printf '%s\n' "The Python release distributions were not created." >&2
        exit 1
    fi
    printf '%s\n' "Python release distributions created in $PROJECT_DIR/dist"
    exit 0
fi

case "$REQUESTED_TARGET" in
    '' | *[!a-z0-9-]*)
        printf 'Invalid build target: %s\n' "$REQUESTED_TARGET" >&2
        exit 2
        ;;
esac
TARGET_PROFILE="$PROJECT_DIR/packaging/targets/$REQUESTED_TARGET.conf"
if [ ! -f "$TARGET_PROFILE" ]; then
    printf 'Unknown build target %s. Available targets:\n' "$REQUESTED_TARGET" >&2
    for profile in "$PROJECT_DIR"/packaging/targets/*.conf; do
        basename "$profile" .conf >&2
    done
    exit 2
fi
# Profiles are version-controlled build configuration, not user input.
. "$TARGET_PROFILE"

CACHE_DIR="$PROJECT_DIR/.build-cache"
PYTHON_ARCHIVE="$CACHE_DIR/$PYTHON_ARCHIVE_NAME"
BUNDLE="$PROJECT_DIR/dist/pocket-harbor-$RELEASE_VERSION-$TARGET_ID-$TARGET_ARCH.zip"
WORK_DIR=$(mktemp -d "/tmp/pocket-harbor-$TARGET_ID-$TARGET_ARCH.XXXXXX")

cleanup() {
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT HUP INT TERM

mkdir -p "$CACHE_DIR"
rm -f "$BUNDLE" "$WHEEL"

if [ "$BUILD_MODE" = all ]; then
    rm -f "$SDIST"
    uv lock
    uv build
else
    uv lock --check
    uv build --wheel
fi

printf 'Downloading a fresh %s Python build for %s...\n' "$TARGET_ARCH" "$TARGET_DISPLAY_NAME"
if command -v curl >/dev/null 2>&1; then
    curl -L --fail --show-error "$PYTHON_URL" -o "$PYTHON_ARCHIVE"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$PYTHON_ARCHIVE" "$PYTHON_URL"
else
    printf '%s\n' "curl or wget is required." >&2
    exit 1
fi

if ! docker run --rm --platform "$DOCKER_PLATFORM" "$SMOKE_IMAGE" /bin/true >/dev/null 2>&1; then
    printf 'Registering Docker emulation support for %s...\n' "$TARGET_ARCH"
    docker run --privileged --rm tonistiigi/binfmt --install "$TARGET_ARCH"
fi

printf 'Building Pocket Harbor for %s %s...\n' "$TARGET_DISPLAY_NAME" "$TARGET_ARCH"
docker build \
    --no-cache \
    --platform "$DOCKER_PLATFORM" \
    --build-arg "APP_VERSION=$RELEASE_VERSION" \
    --build-arg "APPLICATION_DIRECTORY=$APPLICATION_DIRECTORY" \
    --build-arg "BUILDER_IMAGE=$BUILDER_IMAGE" \
    --build-arg "EXECUTABLE_NAME=$EXECUTABLE_NAME" \
    --build-arg "PYTHON_ARCHIVE_NAME=$PYTHON_ARCHIVE_NAME" \
    --file "$PROJECT_DIR/$DOCKERFILE" \
    --output "type=local,dest=$WORK_DIR/export" \
    "$PROJECT_DIR"

EXECUTABLE="$WORK_DIR/export/$APPLICATION_DIRECTORY/$EXECUTABLE_NAME"
if ! file "$EXECUTABLE" | tr ' ' '_' | grep -q "$FILE_ARCH_PATTERN"; then
    printf 'The generated executable is not Linux %s.\n' "$TARGET_ARCH" >&2
    file "$EXECUTABLE" >&2
    exit 1
fi

printf '%s\n' "Testing the exported application without the builder's Python installation..."
SMOKE_VERSION=$(
    docker run \
        --rm \
        --platform "$DOCKER_PLATFORM" \
        --volume "$WORK_DIR/export/$APPLICATION_DIRECTORY:/app:ro" \
        "$SMOKE_IMAGE" \
        "/app/$EXECUTABLE_NAME" --version
)
if [ "$SMOKE_VERSION" != "$FROZEN_VERSION_COMMAND $RELEASE_VERSION" ]; then
    printf 'Clean %s smoke test returned %s instead of %s %s.\n' \
        "$TARGET_ARCH" "$SMOKE_VERSION" "$FROZEN_VERSION_COMMAND" "$RELEASE_VERSION" >&2
    exit 1
fi

mkdir -p "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$APPLICATION_DIRECTORY"
cp -R "$WORK_DIR/export/$APPLICATION_DIRECTORY/." \
    "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$APPLICATION_DIRECTORY/"
cp "$WORK_DIR/export/ca-certificates.crt" \
    "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$APPLICATION_DIRECTORY/ca-certificates.crt"
cp "$PROJECT_DIR/$LAUNCHER_SOURCE" "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$LAUNCHER_NAME"
chmod +x \
    "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$LAUNCHER_NAME" \
    "$WORK_DIR/bundle/$TOOLS_DIRECTORY/$APPLICATION_DIRECTORY/$EXECUTABLE_NAME"

(cd "$WORK_DIR/bundle" && zip -qr "$BUNDLE" "$TOOLS_DIRECTORY")

if [ ! -f "$BUNDLE" ]; then
    printf '%s\n' "The $TARGET_DISPLAY_NAME release artifact was not created." >&2
    exit 1
fi
if [ "$BUILD_MODE" = all ] && { [ ! -f "$WHEEL" ] || [ ! -f "$SDIST" ]; }; then
    printf '%s\n' "One or more Python release distributions were not created." >&2
    exit 1
fi

printf '%s\n' "$TARGET_DISPLAY_NAME release artifact created in $PROJECT_DIR/dist"
file "$EXECUTABLE"
