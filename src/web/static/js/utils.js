/**
 * PlexAniBridge Web UI Utilities
 */

// Global utilities
window.PlexAniBridge = {
    // Utility functions
    utils: {
        /**
         * Format relative time (e.g., "2 hours ago")
         */
        formatRelativeTime(dateString) {
            if (!dateString) return 'Never';

            const date = new Date(dateString);
            const now = new Date();
            const diffMs = now - date;
            const diffSecs = Math.floor(diffMs / 1000);
            const diffMins = Math.floor(diffSecs / 60);
            const diffHours = Math.floor(diffMins / 60);
            const diffDays = Math.floor(diffHours / 24);

            if (diffSecs < 60) return 'just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            if (diffDays < 7) return `${diffDays}d ago`;

            return date.toLocaleDateString();
        },

        /**
         * Format file size in human readable format
         */
        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';

            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));

            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        },

        /**
         * Debounce function calls
         */
        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        /**
         * Throttle function calls
         */
        throttle(func, limit) {
            let inThrottle;
            return function () {
                const args = arguments;
                const context = this;
                if (!inThrottle) {
                    func.apply(context, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            }
        },

        /**
         * Copy text to clipboard
         */
        async copyToClipboard(text) {
            try {
                await navigator.clipboard.writeText(text);
                return true;
            } catch (err) {
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    return true;
                } catch (fallbackErr) {
                    return false;
                } finally {
                    document.body.removeChild(textArea);
                }
            }
        },

        /**
         * Show toast notification
         */
        showToast(message, type = 'info', duration = 5000) {
            const toast = document.createElement('div');
            toast.className = `fixed bottom-4 right-4 z-50 p-4 rounded-lg shadow-lg transition-all duration-300 transform translate-y-full opacity-0`;

            const typeClasses = {
                success: 'bg-green-600 text-white',
                error: 'bg-red-600 text-white',
                warning: 'bg-yellow-600 text-white',
                info: 'bg-blue-600 text-white'
            };

            toast.className += ` ${typeClasses[type] || typeClasses.info}`;
            toast.textContent = message;

            document.body.appendChild(toast);

            // Animate in
            setTimeout(() => {
                toast.classList.remove('translate-y-full', 'opacity-0');
            }, 10);

            // Auto remove
            setTimeout(() => {
                toast.classList.add('translate-y-full', 'opacity-0');
                setTimeout(() => {
                    if (toast.parentNode) {
                        toast.parentNode.removeChild(toast);
                    }
                }, 300);
            }, duration);
        }
    },

    // WebSocket manager
    ws: {
        connection: null,
        connected: false,
        reconnectAttempts: 0,
        maxReconnectAttempts: 5,
        listeners: new Map(),

        connect() {
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/status/`;

                this.connection = new WebSocket(wsUrl);

                this.connection.onopen = () => {
                    this.connected = true;
                    this.reconnectAttempts = 0;
                    console.log('WebSocket connected');
                    this.emit('connected');
                };

                this.connection.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        this.handleMessage(data);
                    } catch (err) {
                        console.error('Error parsing WebSocket message:', err);
                    }
                };

                this.connection.onclose = () => {
                    this.connected = false;
                    this.emit('disconnected');
                    this.scheduleReconnect();
                };

                this.connection.onerror = (error) => {
                    console.error('WebSocket error:', error);
                    this.emit('error', error);
                };
            } catch (error) {
                console.error('WebSocket connection failed:', error);
                this.scheduleReconnect();
            }
        },

        disconnect() {
            if (this.connection) {
                this.connection.close();
                this.connection = null;
            }
            this.connected = false;
        },

        scheduleReconnect() {
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);

                setTimeout(() => {
                    if (!this.connected) {
                        console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                        this.connect();
                    }
                }, delay);
            } else {
                console.warn('Max reconnection attempts reached');
                this.emit('max_reconnects_reached');
            }
        },

        handleMessage(data) {
            this.emit('message', data);

            if (data.type === 'status_update') {
                this.emit('status_update', data.data);
                // Trigger HTMX refresh for status components
                htmx.trigger('#status-components', 'refresh');
            } else if (data.type === 'sync_event') {
                this.emit('sync_event', data);
                PlexAniBridge.utils.showToast(
                    `Sync ${data.event_type} for profile ${data.profile_name}`,
                    data.event_type === 'completed' ? 'success' : 'info'
                );
            }
        },

        on(event, callback) {
            if (!this.listeners.has(event)) {
                this.listeners.set(event, []);
            }
            this.listeners.get(event).push(callback);
        },

        off(event, callback) {
            if (this.listeners.has(event)) {
                const callbacks = this.listeners.get(event);
                const index = callbacks.indexOf(callback);
                if (index > -1) {
                    callbacks.splice(index, 1);
                }
            }
        },

        emit(event, data = null) {
            if (this.listeners.has(event)) {
                this.listeners.get(event).forEach(callback => {
                    try {
                        callback(data);
                    } catch (err) {
                        console.error(`Error in WebSocket event handler for ${event}:`, err);
                    }
                });
            }
        }
    },

    // API helper
    api: {
        async request(url, options = {}) {
            const defaultOptions = {
                headers: {
                    'Content-Type': 'application/json',
                },
            };

            const mergedOptions = { ...defaultOptions, ...options };

            try {
                const response = await fetch(url, mergedOptions);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({}));
                    throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
                }

                return await response.json();
            } catch (error) {
                console.error('API request failed:', error);
                throw error;
            }
        },

        async get(url) {
            return this.request(url);
        },

        async post(url, data) {
            return this.request(url, {
                method: 'POST',
                body: JSON.stringify(data),
            });
        },

        async put(url, data) {
            return this.request(url, {
                method: 'PUT',
                body: JSON.stringify(data),
            });
        },

        async delete(url) {
            return this.request(url, {
                method: 'DELETE',
            });
        }
    }
};

// Alpine.js global functions
window.formatRelativeTime = PlexAniBridge.utils.formatRelativeTime;
window.formatFileSize = PlexAniBridge.utils.formatFileSize;
window.showToast = PlexAniBridge.utils.showToast;

// Initialize WebSocket connection when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    PlexAniBridge.ws.connect();

    // Add connection status indicator
    const statusElement = document.getElementById('connection-status');
    if (statusElement) {
        PlexAniBridge.ws.on('connected', () => {
            statusElement.className = 'h-2 w-2 bg-green-500 rounded-full pulse-blue';
            statusElement.title = 'Connected';
        });

        PlexAniBridge.ws.on('disconnected', () => {
            statusElement.className = 'h-2 w-2 bg-red-500 rounded-full';
            statusElement.title = 'Disconnected';
        });

        PlexAniBridge.ws.on('max_reconnects_reached', () => {
            statusElement.className = 'h-2 w-2 bg-gray-500 rounded-full';
            statusElement.title = 'Connection failed';
        });
    }
});

// HTMX configuration
document.addEventListener('DOMContentLoaded', () => {
    // Configure HTMX
    htmx.config.globalViewTransitions = true;
    htmx.config.defaultSwapStyle = 'innerHTML';
    htmx.config.scrollBehavior = 'smooth';

    // Add loading states to HTMX requests
    document.body.addEventListener('htmx:beforeRequest', (event) => {
        const target = event.target;
        if (target.classList.contains('btn')) {
            target.classList.add('btn-loading');
            target.disabled = true;
        }
    });

    document.body.addEventListener('htmx:afterRequest', (event) => {
        const target = event.target;
        if (target.classList.contains('btn')) {
            target.classList.remove('btn-loading');
            target.disabled = false;
        }
    });

    // Handle HTMX errors
    document.body.addEventListener('htmx:responseError', (event) => {
        const xhr = event.detail.xhr;
        let message = 'Request failed';

        try {
            const errorData = JSON.parse(xhr.responseText);
            message = errorData.detail || message;
        } catch (e) {
            message = `HTTP ${xhr.status}: ${xhr.statusText}`;
        }

        PlexAniBridge.utils.showToast(message, 'error');
    });

    document.body.addEventListener('htmx:sendError', (event) => {
        PlexAniBridge.utils.showToast('Network error - please check your connection', 'error');
    });

    document.body.addEventListener('htmx:timeout', (event) => {
        PlexAniBridge.utils.showToast('Request timed out', 'warning');
    });
});

// Keyboard shortcuts
document.addEventListener('keydown', (event) => {
    // Global shortcuts
    if (event.ctrlKey || event.metaKey) {
        switch (event.key) {
            case 'r':
                // Ctrl/Cmd + R: Refresh current page data
                event.preventDefault();
                htmx.trigger(document.body, 'refresh');
                PlexAniBridge.utils.showToast('Page refreshed', 'info', 2000);
                break;

            case 'k':
                // Ctrl/Cmd + K: Focus search (if available)
                event.preventDefault();
                const searchInput = document.querySelector('input[type="search"], input[placeholder*="search" i]');
                if (searchInput) {
                    searchInput.focus();
                }
                break;
        }
    }

    // Escape key: Close modals, clear search, etc.
    if (event.key === 'Escape') {
        // Close any open Alpine.js modals
        window.dispatchEvent(new CustomEvent('close-modal'));

        // Clear search inputs
        const activeElement = document.activeElement;
        if (activeElement && activeElement.tagName === 'INPUT') {
            activeElement.blur();
        }
    }
});

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PlexAniBridge;
}