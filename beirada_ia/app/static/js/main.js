const stream = document.getElementById("camera-stream");
const offline = document.getElementById("camera-offline");

const statusText = document.getElementById("status-text");
const statusFooter = document.getElementById("status-footer");
const statusDot = document.getElementById("status-dot");

function setOnline() {

    offline.classList.remove("active");

    statusText.textContent = "Online";
    statusFooter.textContent = "Online";

    statusDot.className = "dot online";
}

function setOffline() {

    offline.classList.add("active");

    statusText.textContent = "Offline";
    statusFooter.textContent = "Offline";

    statusDot.className = "dot offline";
}

stream.onload = () => {
    setOnline();
};

stream.onerror = () => {
    setOffline();
};

async function updateMetrics() {

    try {

        const response = await fetch("/metrics");
        const data = await response.json();

        document.getElementById("requests").textContent =
            data.total_requests;

        document.getElementById("latency").textContent =
            `${data.avg_inference_ms} ms`;

    } catch (err) {

        console.error(err);

    }
}

updateMetrics();

setInterval(updateMetrics, 2000);