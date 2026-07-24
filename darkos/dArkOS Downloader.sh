#!/bin/sh
# Copy-only dArkOS R36S launcher for the bundled Linux ARM64 executable.
set -eu

SCRIPT_DIR=$(CDPATH= cd "$(dirname "$0")" && pwd)
LAUNCHER="$SCRIPT_DIR/dArkOS Downloader.sh"
APP_DIR="$SCRIPT_DIR/darkos-downloader"
EXECUTABLE="$APP_DIR/darkos-downloader"
LOG_FILE="$APP_DIR/darkos-downloader.log"
REFRESH_FILE="$APP_DIR/.refresh-emulationstation"
CA_BUNDLE="$APP_DIR/ca-certificates.crt"
UPDATE_DIR="$SCRIPT_DIR/.darkos-downloader-update"
UPDATE_BACKUP="$SCRIPT_DIR/.darkos-downloader-backup"
UPDATE_LAUNCHER_TEMP="$SCRIPT_DIR/.darkos-downloader-launcher.new"

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

show_update_message() {
    title=$1
    message=$2
    if command -v dialog >/dev/null 2>&1; then
        dialog --clear --title "$title" --msgbox "$message" 10 64
    else
        clear 2>/dev/null || true
        printf '\n%s\n\n%s\n\n' "$title" "$message"
        printf 'Press Enter to return...'
        read -r _answer
    fi
}

apply_pending_update() {
    ready_file="$UPDATE_DIR/.ready"
    staged_app="$UPDATE_DIR/darkos-downloader"
    staged_executable="$staged_app/darkos-downloader"
    staged_launcher="$UPDATE_DIR/dArkOS Downloader.sh"

    if [ ! -f "$ready_file" ]; then
        return 1
    fi
    update_version=$(sed -n '1p' "$ready_file" 2>/dev/null || true)
    if [ ! -f "$staged_executable" ] || [ ! -f "$staged_launcher" ]; then
        printf '%s\n' "A staged update is incomplete; keeping the installed version." >>"$LOG_FILE"
        rm -rf "$UPDATE_DIR"
        show_update_message \
            "dArkOS Downloader update failed" \
            "The downloaded update was incomplete. The installed version was not changed."
        return 2
    fi

    rm -f "$UPDATE_LAUNCHER_TEMP"
    if ! cp "$staged_launcher" "$UPDATE_LAUNCHER_TEMP"; then
        printf '%s\n' "Could not prepare the updated Tools launcher." >>"$LOG_FILE"
        show_update_message \
            "dArkOS Downloader update failed" \
            "The new launcher could not be prepared. The installed version was not changed."
        return 2
    fi
    chmod +x "$UPDATE_LAUNCHER_TEMP" "$staged_executable" 2>/dev/null || true

    rm -rf "$UPDATE_BACKUP"
    if ! mv "$APP_DIR" "$UPDATE_BACKUP"; then
        rm -f "$UPDATE_LAUNCHER_TEMP"
        show_update_message \
            "dArkOS Downloader update failed" \
            "The installed application could not be backed up. It was not changed."
        return 2
    fi
    if ! mv "$staged_app" "$APP_DIR"; then
        mv "$UPDATE_BACKUP" "$APP_DIR" 2>/dev/null || true
        rm -f "$UPDATE_LAUNCHER_TEMP"
        show_update_message \
            "dArkOS Downloader update failed" \
            "The new application could not be installed. The previous version was restored."
        return 2
    fi
    if [ -d "$UPDATE_BACKUP/.downloads" ]; then
        rm -rf "$APP_DIR/.downloads"
        if ! mv "$UPDATE_BACKUP/.downloads" "$APP_DIR/.downloads"; then
            rm -rf "$APP_DIR"
            mv "$UPDATE_BACKUP" "$APP_DIR" 2>/dev/null || true
            rm -f "$UPDATE_LAUNCHER_TEMP"
            show_update_message \
                "dArkOS Downloader update failed" \
                "Settings could not be preserved. The previous version was restored."
            return 2
        fi
    fi
    if ! mv "$UPDATE_LAUNCHER_TEMP" "$LAUNCHER"; then
        if [ -d "$APP_DIR/.downloads" ]; then
            mv "$APP_DIR/.downloads" "$UPDATE_BACKUP/.downloads" 2>/dev/null || true
        fi
        rm -rf "$APP_DIR"
        mv "$UPDATE_BACKUP" "$APP_DIR" 2>/dev/null || true
        show_update_message \
            "dArkOS Downloader update failed" \
            "The Tools launcher could not be updated. The previous version was restored."
        return 2
    fi

    rm -rf "$UPDATE_BACKUP" "$UPDATE_DIR"
    printf 'Updated dArkOS Downloader to v%s.\n' "$update_version" >>"$LOG_FILE"
    show_update_message \
        "dArkOS Downloader updated" \
        "Version $update_version is installed. Reopen the tool to use it."
    return 0
}

if [ ! -f "$EXECUTABLE" ] && [ -f "$UPDATE_BACKUP/darkos-downloader" ]; then
    rm -rf "$APP_DIR"
    mv "$UPDATE_BACKUP" "$APP_DIR" 2>/dev/null || true
fi

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
export DW_INSTALL_DIR="$APP_DIR"
export DW_ES_REFRESH_FILE="$REFRESH_FILE"
export TERM="${TERM:-xterm-256color}"
if [ -f "$CA_BUNDLE" ]; then
    export SSL_CERT_FILE="$CA_BUNDLE"
fi

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

    set +e
    apply_pending_update
    update_status=$?
    set -e
    refresh_emulationstation
    if [ "$status" -ne 0 ]; then
        show_failure "$status"
    elif [ "$update_status" -eq 2 ]; then
        status=1
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
