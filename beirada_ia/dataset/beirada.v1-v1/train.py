from ultralytics import YOLO

# Modelo base
model = YOLO("yolov8n_v3.pt")

# Treinamento
results = model.train(
    data="data.yaml",
    epochs=100,
    imgsz=1300,
    batch=16,
    workers=4,
    device=0,
    project="runs",
    name="yolo-epi_custom"
)

print("Treinamento concluído!")
print("Melhor modelo:")
print("runs/yolo-epi_custom/weights/best.pt")