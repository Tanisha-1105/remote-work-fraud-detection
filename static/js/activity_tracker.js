// activity_tracker.js
// BROWSER ACTIVITY TRACKER (Standalone File)
// Tracks mouse, keyboard, and idle time *within this browser tab only*.

// --- Configuration ---
// Retrieve employee ID from the hidden field in dashboard.html
const EMPLOYEE_ID = document.getElementById('employee-id')?.value; 
const LOG_INTERVAL_MS = 15000; // Log activity every 15 seconds
const MAX_IDLE_TIME_MS = 60000; // 60 seconds of real idle time before counting

// --- State Variables ---
let trackingActive = true;
let mouseCount = 0;
let keystrokeCount = 0;
let lastActivityTime = Date.now();
let totalSessionActivity = 0;
let totalSessionIdle = 0;
let logInterval;
let sessionStart;
let isPageActive = true; // Tracks if the monitoring page is currently focused

//DOM Elements
const mouseCountEl = document.getElementById('mouse-count');
const keystrokeCountEl = document.getElementById('keystroke-count');
const statusDotEl = document.getElementById('status-dot');
const statusTextEl = document.getElementById('status-text');
const trackingCardEl = document.getElementById('tracking-status-card');
const prodScoreEl = document.getElementById('productivity-score');
const prodBarEl = document.getElementById('productivity-bar');
const idleTimeDisplayEl = document.getElementById('idle-time-display');
const sessionTimeEl = document.getElementById('session-time');
const startTimeEl = document.getElementById('start-time');
const logListEl = document.getElementById('log-list');
const activeWindowDisplayEl = document.getElementById('active-window-display');
const deviceIdEl = document.getElementById('device-id');

//Helper Functions
function formatTime(seconds) {
    const h = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const m = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const s = String(seconds % 60).padStart(2, '0');
    return `${h}:${m}:${s}`;
}

function simpleHash(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) - hash) + str.charCodeAt(i);
        hash |= 0;
    }
    return Math.abs(hash).toString(16).slice(0, 8).toUpperCase();
}

function setDeviceId() {
    const agent = navigator.userAgent;
    const hash = simpleHash(agent);
    if (deviceIdEl) deviceIdEl.textContent = "BROWSER-" + hash;
}

//Session Timer Functions
function updateSessionTimer() {
    if (!sessionStart) return;
    const elapsedSeconds = Math.floor((Date.now() - sessionStart) / 1000);
    if (sessionTimeEl) sessionTimeEl.textContent = formatTime(elapsedSeconds);
}

//Input Handling
function handleActivity() {
    if (!trackingActive) return;
    lastActivityTime = Date.now();
}

document.addEventListener('mousemove', () => { mouseCount++; handleActivity(); });
document.addEventListener('click', () => { mouseCount++; handleActivity(); });
document.addEventListener('keydown', (e) => {
    //Filter out control keys to focus on productive input
    if (!e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1) {
        keystrokeCount++; 
        handleActivity();
    }
});

//Tracking Logic
function updateTelemetryDisplay() {
    if (mouseCountEl) mouseCountEl.textContent = mouseCount;
    if (keystrokeCountEl) keystrokeCountEl.textContent = keystrokeCount;
    if (idleTimeDisplayEl) idleTimeDisplayEl.textContent = totalSessionIdle; 
    if (activeWindowDisplayEl) activeWindowDisplayEl.textContent = document.title;
}

function calculateProductivity() {
    const totalActivity = totalSessionActivity;
    const totalTime = totalActivity + totalSessionIdle;
    
    let score = 0;
    if (totalTime > 0) {
        score = Math.round((totalActivity / totalTime) * 100);
    }
    
    //Update score elements
    if (prodScoreEl) prodScoreEl.textContent = `${score}%`;
    if (prodBarEl) {
        prodBarEl.style.width = `${Math.min(100, score)}%`;
        //Dynamic color based on score
        prodBarEl.className = `progress-bar bg-${score >= 75 ? 'success' : score >= 50 ? 'warning' : 'danger'}`;
    }
}

function logAndResetActivity() {
    if (!trackingActive || !EMPLOYEE_ID) return;
    
    const timeSinceLastActivity = Date.now() - lastActivityTime; 
    const intervalDurationSeconds = LOG_INTERVAL_MS / 1000;
    let currentIdleSeconds = 0;
    
    //Logic: If user hasn't touched the input devices in MAX_IDLE_TIME_MS, consider the interval idle.
    if (timeSinceLastActivity > MAX_IDLE_TIME_MS) {
        currentIdleSeconds = intervalDurationSeconds;
    } else {
        currentIdleSeconds = 0;
    }

    //Prepare data for API 
    const data = {
        employee_id: EMPLOYEE_ID,
        mouse_activity: mouseCount,
        keyboard_activity: keystrokeCount,
        idle_time: currentIdleSeconds,
        active_window_title: document.title //Capture browser title
    };

    //Update session totals based on the outcome of the interval
    totalSessionActivity += mouseCount + keystrokeCount;
    totalSessionIdle += currentIdleSeconds;

    //Send data to Flask backend
    fetch('/api/log-activity', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(res => {
        console.log("Browser Activity logged:", res);
        
        //Add local log entry for user feedback
        const dateStr = new Date().toLocaleTimeString();
        const logBadgeColor = data.idle_time < 10 ? 'success' : 'warning';
        
        const logHtml = `
            <div class="log-item p-3 border-bottom d-flex justify-content-between">
                <div>
                    <small class="text-muted d-block">${dateStr}</small>
                    <strong>M: ${data.mouse_activity} | K: ${data.keyboard_activity} | I: ${data.idle_time}s</strong>
                    <div class="small text-truncate text-muted">Window: ${data.active_window_title}</div>
                </div>
                <span class="badge bg-${logBadgeColor} align-self-center">
                    Browser Log
                </span>
            </div>`;
            
        //Insert new log entry at the top of the list
        if (logListEl) {
            logListEl.insertAdjacentHTML('afterbegin', logHtml);
            
            //Keep only the last 10 logs visible
            while (logListEl.children.length > 10) {
                logListEl.lastChild.remove();
            }
        }
        
        //Recalculate and update UI based on new totals
        calculateProductivity();
        updateTelemetryDisplay();
    })
    .catch(err => console.error("Error logging browser activity:", err));

    //Reset counters for next interval
    mouseCount = 0;
    keystrokeCount = 0;
}

//Tracking Control
window.toggleTracking = function() {
    trackingActive = !trackingActive;
    const btn = document.getElementById('toggle-tracking');
    
    if (trackingActive) {
        if (trackingCardEl) trackingCardEl.classList.remove('status-inactive');
        if (statusDotEl) statusDotEl.classList.add('active');
        if (statusTextEl) statusTextEl.textContent = 'Active Monitoring';
        if (btn) {
            btn.classList.add('btn-success');
            btn.classList.remove('btn-danger');
            btn.innerHTML = '<i class="bi bi-pause"></i>';
        }
        logInterval = setInterval(logAndResetActivity, LOG_INTERVAL_MS);
        lastActivityTime = Date.now(); //Reset activity time when starting
    } else {
        if (trackingCardEl) trackingCardEl.classList.add('status-inactive');
        if (statusDotEl) statusDotEl.classList.remove('active');
        if (statusTextEl) statusTextEl.textContent = 'Monitoring Paused';
        if (btn) {
            btn.classList.add('btn-danger');
            btn.classList.remove('btn-success');
            btn.innerHTML = '<i class="bi bi-play"></i>';
        }
        clearInterval(logInterval);
        //Ensure counters are reset when paused
        mouseCount = 0;
        keystrokeCount = 0;
    }
}

//Initialization
document.addEventListener('DOMContentLoaded', () => {
    sessionStart = Date.now();
    if (startTimeEl) startTimeEl.textContent = new Date(sessionStart).toLocaleTimeString();
    setInterval(updateSessionTimer, 1000);
    
    setDeviceId();

    //Start tracking immediately
    window.toggleTracking();
    
    //Set initial button icon to pause/monitoring state
    const btn = document.getElementById('toggle-tracking');
    if (btn) btn.innerHTML = '<i class="bi bi-pause"></i>';
});