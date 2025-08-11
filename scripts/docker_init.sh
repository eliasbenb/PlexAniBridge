#!/usr/bin/env sh

PUID=${PUID:-1000}
PGID=${PGID:-1000}
UMASK=${UMASK:-022}

log() {
    printf "%s - init - INFO\t%s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

if ! getent group abc >/dev/null 2>&1; then
    addgroup -g "$PGID" abc
fi

if ! getent passwd abc >/dev/null 2>&1; then
    adduser -u "$PUID" -G abc -s /bin/sh -D abc
fi

chown -R "$PUID:$PGID" /app
if [ -d "/config" ]; then
    chown -R "$PUID:$PGID" /config
fi

if printf '%s' "$UMASK" | grep -Eq '^[0-7]{3,4}$'; then
    umask "$UMASK"
else
    log "Invalid UMASK '$UMASK' provided, falling back to 022"
    umask 022
fi

CURRENT_UMASK=$(umask)
log "Starting PlexAniBridge (UID: $PUID, GID: $PGID, UMASK: $CURRENT_UMASK)"

exec su-exec abc "$@"
