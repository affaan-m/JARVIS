"""
One-time script: export yolo11n.pt -> yolo11n.onnx at imgsz=320.
Run once before deployment:  python export_onnx.py
"""

from ultralytics import YOLO

model = YOLO("yolo11n.pt")
model.export(format="onnx", imgsz=320, simplify=True)
print("Exported yolo11n.onnx (imgsz=320)")
