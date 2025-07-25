#!/usr/bin/env sh

PUID=${PUID:-1000}
PGID=${PGID:-1000}

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

umask 022

log "Starting PlexAniBridge (UID: $PUID, GID: $PGID)"

exec su-exec abc "$@"
