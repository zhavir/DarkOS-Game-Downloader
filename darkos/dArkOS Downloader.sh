#!/bin/sh
# Copy-only dArkOS R36S launcher for the bundled Linux ARM64 executable.
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
APP_DIR="$SCRIPT_DIR/darkos-downloader"
EXECUTABLE="$APP_DIR/darkos-downloader"
LOG_FILE="$APP_DIR/darkos-downloader.log"
REFRESH_FILE="$APP_DIR/.refresh-emulationstation"

show_failure() {
    message="dArkOS Downloader stopped with exit code $1.\n\nDiagnostic log:\n$LOG_FILE"
    if command -v dialog >/dev/null 2>&1; then
        dialog --clear --title "dArkOS Downloader" --msgbox "$message" 12 64
        dialog --clear --title "Diagnostic log" --textbox "$LOG_FILE" 20 70
    else
        clear 2>/dev/null || true
        printf '\ndArkOS Downloader could not start.\n\n'
        tail -n 30 "$LOG_FILE" 2>/dev/null || true
        printf '\nPress Enter to return...'
        read -r _answer
    fi
}

if [ ! -f "$EXECUTABLE" ]; then
    clear 2>/dev/null || true
    printf '\ndArkOS Downloader is incomplete.\n\n'
    printf 'Copy the complete tools folder to the ROM card again.\n\n'
    printf 'Press Enter to return...'
    read -r _answer
    exit 1
fi

architecture=$(uname -m 2>/dev/null || printf unknown)
case "$architecture" in
    aarch64 | arm64)
        ;;
    *)
        printf 'Unsupported architecture: %s\n' "$architecture" >"$LOG_FILE"
        show_failure 126
        exit 126
        ;;
esac

mkdir -p "$APP_DIR/.downloads"
export DW_DOWNLOAD_DIR="${DW_DOWNLOAD_DIR:-$APP_DIR/.downloads}"
export DW_ES_REFRESH_FILE="$REFRESH_FILE"
export TERM="${TERM:-xterm-256color}"

refresh_emulationstation() {
    if [ ! -f "$REFRESH_FILE" ]; then
        return
    fi
    rm -f "$REFRESH_FILE"
    printf '%s\n' "A game-list refresh was requested. Restarting EmulationStation." >>"$LOG_FILE"

    if ! command -v systemctl >/dev/null 2>&1; then
        printf '%s\n' "systemctl is unavailable; use Select > Update Games Lists." >>"$LOG_FILE"
        return
    fi
    if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
        sudo -n systemctl --no-block restart emulationstation >>"$LOG_FILE" 2>&1 || true
    else
        systemctl --no-block restart emulationstation >>"$LOG_FILE" 2>&1 || true
    fi
}

run_application() {
    cd "$APP_DIR"
    chmod +x "$EXECUTABLE" 2>/dev/null || true
    clear 2>/dev/null || true

    set +e
    "$EXECUTABLE" 2>>"$LOG_FILE"
    status=$?
    set -e

    refresh_emulationstation
    if [ "$status" -ne 0 ]; then
        show_failure "$status"
    fi
    clear 2>/dev/null || true
    return "$status"
}

# openvt starts this internal mode on a real Linux virtual console.  dArkOS and
# dArkOSRE normally start Tools scripts with stdin/stdout detached from a TTY.
if [ "${1:-}" = "--run-on-vt" ]; then
    {
        printf 'Virtual console stdin tty: %s\n' "$(test -t 0 && printf yes || printf no)"
        printf 'Virtual console stdout tty: %s\n' "$(test -t 1 && printf yes || printf no)"
    } >>"$LOG_FILE"
    run_application
    exit $?
fi

{
    printf 'dArkOS Downloader diagnostic log\n'
    printf 'Architecture: %s\n' "$architecture"
    printf 'Kernel: '
    uname -sr 2>/dev/null || true
    printf 'Terminal: %s\n' "$TERM"
    printf 'stdin tty: %s\n' "$(test -t 0 && printf yes || printf no)"
    printf 'stdout tty: %s\n' "$(test -t 1 && printf yes || printf no)"
    if command -v getconf >/dev/null 2>&1; then
        getconf GNU_LIBC_VERSION 2>/dev/null || true
    fi
    printf '\nApplication output:\n'
} >"$LOG_FILE"

if test -t 0 && test -t 1; then
    run_application
    exit $?
fi

if (: </dev/tty) 2>/dev/null; then
    set +e
    run_application </dev/tty >/dev/tty
    status=$?
    set -e
    exit "$status"
fi

printf 'No controlling terminal was supplied by the Tools menu. Starting openvt.\n' >>"$LOG_FILE"
if ! command -v openvt >/dev/null 2>&1; then
    printf 'openvt is not installed; a Linux virtual console cannot be created.\n' >>"$LOG_FILE"
    show_failure 127
    exit 127
fi

previous_vt=""
if command -v fgconsole >/dev/null 2>&1; then
    previous_vt=$(fgconsole 2>/dev/null || true)
    if [ -z "$previous_vt" ] && command -v sudo >/dev/null 2>&1; then
        previous_vt=$(sudo -n fgconsole 2>/dev/null || true)
    fi
fi

set +e
if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo -n openvt -s -f -w -- /bin/sh "$0" --run-on-vt
else
    openvt -s -f -w -- /bin/sh "$0" --run-on-vt
fi
status=$?
set -e

case "$previous_vt" in
    '' | *[!0-9]*)
        ;;
    *)
        if command -v chvt >/dev/null 2>&1; then
            if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
                sudo -n chvt "$previous_vt" 2>/dev/null || true
            else
                chvt "$previous_vt" 2>/dev/null || true
            fi
        fi
        ;;
esac

if [ "$status" -ne 0 ]; then
    printf 'openvt or the application returned exit code %s.\n' "$status" >>"$LOG_FILE"
fi
exit "$status"
