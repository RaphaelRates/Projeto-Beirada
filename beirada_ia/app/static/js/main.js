const stream = document.getElementById("camera-stream");
const offline = document.getElementById("camera-offline");

const statusText = document.getElementById("status-text");
const statusFooter = document.getElementById("status-footer");
const statusDot = document.getElementById("status-dot");
const imageUpload = document.getElementById("image-upload");
const uploadResult = document.getElementById("upload-result");
const uploadPreview = document.getElementById("upload-preview");
const predictionStatus = document.getElementById("prediction-status");
const predictionTime = document.getElementById("prediction-time");
const predictionList = document.getElementById("prediction-list");

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

        const modelEl = document.getElementById("model");
        if (modelEl && data.model_name) {
            modelEl.textContent = data.model_name;
        }

    } catch (err) {

        console.error(err);

    }
}

updateMetrics();

setInterval(updateMetrics, 2000);

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(",")[1]);
        reader.onerror = () => reject(new Error("Não foi possível ler a imagem."));
        reader.readAsDataURL(file);
    });
}

function showPredictions(detections) {
    predictionList.replaceChildren();

    if (!detections.length) {
        const emptyItem = document.createElement("li");
        emptyItem.textContent = "Nenhum objeto detectado";
        predictionList.appendChild(emptyItem);
        return;
    }

    detections.forEach((detection) => {
        const item = document.createElement("li");
        const label = document.createElement("strong");
        const confidence = document.createElement("span");
        label.textContent = detection.label;
        confidence.textContent = `${(detection.confidence * 100).toFixed(1)}%`;
        item.append(label, confidence);
        predictionList.appendChild(item);
    });
}

imageUpload.addEventListener("change", async () => {
    const file = imageUpload.files[0];
    if (!file) return;

    uploadResult.hidden = false;
    uploadPreview.src = URL.createObjectURL(file);
    predictionStatus.textContent = "Analisando...";
    predictionTime.textContent = "-- ms";
    predictionList.replaceChildren();

    try {
        const imageBase64 = await fileToBase64(file);
        const response = await fetch("/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ image_base64: imageBase64 }),
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "A API não conseguiu analisar a imagem.");
        }

        predictionStatus.textContent = `${data.detections.length} detecção(ões)`;
        predictionTime.textContent = `${data.inference_ms.toFixed(1)} ms`;
        showPredictions(data.detections);
    } catch (error) {
        predictionStatus.textContent = "Erro na análise";
        predictionTime.textContent = "";
        const errorItem = document.createElement("li");
        errorItem.textContent = error.message;
        predictionList.appendChild(errorItem);
    }
});