#!/usr/bin/env sh

PUID=${PUID:-1000}
PGID=${PGID:-1000}

CURRENT_UID=$(id -u abc)
CURRENT_GID=$(id -g abc)

log() {
    printf "%s - init - INFO\t%s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$1"
}

if [ "$PGID" != "$CURRENT_GID" ]; then
    groupmod -g "$PGID" abc
fi

if [ "$PUID" != "$CURRENT_UID" ]; then
    usermod -u "$PUID" abc
fi

chown -R abc:abc /app
if [ -d "/config" ]; then
    chown -R abc:abc /config
fi

umask 022

log "Starting PlexAniBridge (UID: $PUID, GID: $PGID)"

exec su-exec abc "$@"
