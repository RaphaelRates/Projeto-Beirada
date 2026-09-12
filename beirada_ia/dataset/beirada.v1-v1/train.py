from ultralytics import YOLO

# Modelo base
model = YOLO("yolov8n.pt")

# Treinamento
results = model.train(
    data="data.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    workers=4,
    device=0,
    project="runs",
    name="yolov8n_custom"
)

print("Treinamento concluído!")
print("Melhor modelo:")
print("runs/yolov8n_custom/weights/best.pt")