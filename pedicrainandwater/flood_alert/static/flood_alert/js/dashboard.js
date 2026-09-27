/**
 * FloodGuard Dashboard JavaScript
 * - WebSocket real-time alerts
 * - Province region filtering
 * - Toast notifications
 */
(function () {
    'use strict';

    /* ===== WebSocket ===== */
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/alerts/`;
    let ws = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT = 8;

    function connectWebSocket() {
        try {
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('[FloodGuard] WebSocket connected');
                reconnectAttempts = 0;
                updateWsStatus(true);
                // Heartbeat every 30s
                setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ action: 'ping' }));
                    }
                }, 30000);
            };

            ws.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'alert') {
                        handleIncomingAlert(msg.data);
                    }
                } catch (e) {
                    console.warn('[FloodGuard] WS message parse error:', e);
                }
            };

            ws.onclose = () => {
                updateWsStatus(false);
                if (reconnectAttempts < MAX_RECONNECT) {
                    const delay = Math.min(1000 * 2 ** reconnectAttempts, 30000);
                    console.log(`[FloodGuard] WS closed, reconnecting in ${delay}ms...`);
                    setTimeout(connectWebSocket, delay);
                    reconnectAttempts++;
                }
            };

            ws.onerror = (err) => {
                console.warn('[FloodGuard] WS error:', err);
            };

        } catch (e) {
            console.warn('[FloodGuard] WebSocket not available:', e);
        }
    }

    function updateWsStatus(connected) {
        const badge = document.getElementById('ws-status');
        if (!badge) return;
        const dot = badge.querySelector('.status-dot');
        const text = badge.querySelector('span:last-child');
        if (connected) {
            badge.style.background = 'rgba(34, 197, 94, 0.1)';
            badge.style.borderColor = 'rgba(34, 197, 94, 0.3)';
            badge.style.color = '#22c55e';
            if (dot) dot.style.background = '#22c55e';
            if (text) text.textContent = 'เชื่อมต่อ';
        } else {
            badge.style.background = 'rgba(239, 68, 68, 0.1)';
            badge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
            badge.style.color = '#ef4444';
            if (dot) dot.style.background = '#ef4444';
            if (text) text.textContent = 'ขาดการเชื่อมต่อ';
        }
    }

    function handleIncomingAlert(alertData) {
        // Add to alerts list
        prependAlert(alertData);
        // Show toast
        showToast(alertData);
        // Browser notification if permitted
        sendBrowserNotification(alertData);
    }

    function prependAlert(alertData) {
        const container = document.getElementById('alerts-container');
        if (!container) return;

        // Remove empty state if present
        const emptyState = container.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const alertClass = alertData.alert_type
            ? alertData.alert_type.toLowerCase().replace('_', '_') : '';

        const iconMap = {
            'FLOOD_CRITICAL': '🚨',
            'FLOOD_RISK': '⚠️',
            'HEAVY_RAIN': '🌧️',
            'DAM_FULL': '🏞️',
            'DAM_WARNING': '⚠️',
        };
        const icon = iconMap[alertData.alert_type] || '⚠️';

        const now = new Date();
        const timeStr = `${now.getDate().toString().padStart(2,'0')}/${(now.getMonth()+1).toString().padStart(2,'0')}/${now.getFullYear()+543} ${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;

        const el = document.createElement('div');
        el.className = `alert-item alert-${alertClass}`;
        el.dataset.id = alertData.id;
        el.innerHTML = `
            <div class="alert-icon">${icon}</div>
            <div class="alert-body">
                <div class="alert-title">${escapeHtml(alertData.title)}</div>
                <div class="alert-province">📍 ${escapeHtml(alertData.province)}</div>
                <div class="alert-time">🕐 ${timeStr}</div>
            </div>
        `;

        container.insertBefore(el, container.firstChild);

        // Limit to 20 items
        const items = container.querySelectorAll('.alert-item');
        if (items.length > 20) {
            items[items.length - 1].remove();
        }
    }

    /* ===== Toast ===== */
    function showToast(alertData) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const riskClass = {
            'CRITICAL': 'toast-critical',
            'HIGH': 'toast-high',
            'MODERATE': 'toast-moderate',
            'LOW': 'toast-low',
        }[alertData.risk_level] || '';

        const toast = document.createElement('div');
        toast.className = `toast ${riskClass}`;
        toast.innerHTML = `
            <div class="toast-title">${escapeHtml(alertData.title)}</div>
            <div class="toast-body">📍 ${escapeHtml(alertData.province)} | ความน่าจะเป็น: ${alertData.probability}%</div>
        `;

        toast.addEventListener('click', () => toast.remove());

        container.appendChild(toast);

        // Auto remove after 8 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                toast.style.transition = 'all 0.4s ease';
                setTimeout(() => toast.remove(), 400);
            }
        }, 8000);
    }

    /* ===== Browser Notifications ===== */
    function sendBrowserNotification(alertData) {
        if (!('Notification' in window)) return;
        if (Notification.permission === 'granted') {
            new Notification(alertData.title, {
                body: `📍 ${alertData.province} | ความน่าจะเป็น: ${alertData.probability}%`,
                icon: '/static/flood_alert/img/icon.png',
                tag: `flood-${alertData.id}`,
            });
        } else if (Notification.permission !== 'denied') {
            Notification.requestPermission();
        }
    }

    /* ===== Province Filter ===== */
    function initRegionFilter() {
        const filterBtns = document.querySelectorAll('#region-filter .filter-btn');
        const cards = document.querySelectorAll('#provinces-grid .province-card');

        filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                const region = btn.dataset.region;
                cards.forEach(card => {
                    if (region === 'all' || card.dataset.region === region) {
                        card.style.display = 'block';
                    } else {
                        card.style.display = 'none';
                    }
                });
            });
        });
    }

    /* ===== Risk Filter (from Stats Cards) ===== */
    function initRiskFilter() {
        const statCards = document.querySelectorAll('.stats-grid .stat-card');
        const cards = document.querySelectorAll('#provinces-grid .province-card');

        statCards.forEach(card => {
            card.addEventListener('click', () => {
                const riskLevel = card.dataset.risk;
                if (!riskLevel) return;

                // Reset region filter
                const filterBtns = document.querySelectorAll('#region-filter .filter-btn');
                filterBtns.forEach(b => b.classList.remove('active'));
                const allBtn = document.querySelector('#region-filter .filter-btn[data-region="all"]');
                if (allBtn) allBtn.classList.add('active');

                // Filter cards by risk
                cards.forEach(c => {
                    if (riskLevel === 'all' || c.classList.contains(`province-${riskLevel}`)) {
                        c.style.display = 'block';
                    } else {
                        c.style.display = 'none';
                    }
                });

                // Scroll to provinces grid
                const gridSection = document.querySelector('.panel-provinces');
                if (gridSection) {
                    gridSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });
    }

    /* ===== Auto-refresh data every 5 minutes ===== */
    function initAutoRefresh() {
        setInterval(() => {
            // Reload predictions silently
            fetch('/api/predictions/')
                .then(r => r.json())
                .then(data => {
                    console.log(`[FloodGuard] Refreshed ${data.predictions?.length || 0} predictions`);
                })
                .catch(() => {});
        }, 5 * 60 * 1000);
    }

    /* ===== Utils ===== */
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    /* ===== Init ===== */
    document.addEventListener('DOMContentLoaded', () => {
        connectWebSocket();
        initRegionFilter();
        initRiskFilter();
        initAutoRefresh();

        // Request notification permission on first load
        if ('Notification' in window && Notification.permission === 'default') {
            // Wait for user interaction
            document.addEventListener('click', () => {
                Notification.requestPermission();
            }, { once: true });
        }

        console.log('[FloodGuard] Dashboard initialized 🌊');
    });

})();
