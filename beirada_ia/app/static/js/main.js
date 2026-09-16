const stream       = document.getElementById("camera-stream");
const offline      = document.getElementById("camera-offline");

const statusText   = document.getElementById("status-text");
const statusFooter = document.getElementById("status-footer");
const statusDot    = document.getElementById("status-dot");

const STREAM_RETRY_INTERVAL_MS = 5000;
let reconnectTimer = null;

/* ---------- Status ---------- */
function setOnline() {
    offline.classList.remove("active");
    statusText.textContent   = "Online";
    statusFooter.textContent = "Online";
    statusDot.className      = "dot online";
}

function setOffline() {
    offline.classList.add("active");
    statusText.textContent   = "Sem conexão";
    statusFooter.textContent = "Sem conexão";
    statusDot.className      = "dot offline";
}

/* ---------- Stream ---------- */
function scheduleStreamReconnect() {
    if (reconnectTimer !== null) return;

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        stream.src = `/stream/camera?retry=${Date.now()}`;
    }, STREAM_RETRY_INTERVAL_MS);
}

stream.addEventListener("load", () => {
    if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    setOnline();
});

stream.addEventListener("error", () => {
    setOffline();
    scheduleStreamReconnect();
});

/* ---------- Modelo ---------- */
async function updateModel() {
    try {
        const response = await fetch("/metrics");
        const data = await response.json();

        const modelEl = document.getElementById("model");
        if (modelEl && data.model_name) {
            modelEl.textContent = data.model_name;
        }
    } catch (err) {
        console.error(err);
    }
}

updateModel();