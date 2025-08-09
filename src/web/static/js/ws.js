/**
 * WebSocket utility functions.
 */

function getWsBase() {
    const proto = (location.protocol === 'https:') ? 'wss://' : 'ws://';
    return proto + location.host;
}
