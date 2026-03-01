from ultralytics import YOLO
import cv2
import time


def draw_box(frame, x1: int, y1: int, x2: int, y2: int, label: str, color: tuple):
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(frame, (x1, y1 - th - 10), (x1 + tw + 6, y1), color, -1)
    cv2.putText(frame, label, (x1 + 3, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def main():
    model = YOLO("yolo11n.pt")

    frame_count = 0
    fps = 0.0
    fps_update_time = time.time()
    fps_frame_count = 0

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error: Could not open webcam")
        exit(1)

    print("Human detection running. Press [q] to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame")
            break

        frame_count += 1

        # FPS counter
        fps_frame_count += 1
        now = time.time()
        if now - fps_update_time >= 1.0:
            fps = fps_frame_count / (now - fps_update_time)
            fps_frame_count = 0
            fps_update_time = now

        # YOLO tracking — class 0 = person
        results = model.track(
            source=frame,
            classes=[0],
            conf=0.5,
            persist=True,
            verbose=False,
        )

        boxes = results[0].boxes

        for box in boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            track_id = int(box.id[0]) if box.id is not None else None

            label = f"Person"
            if track_id is not None:
                label = f"Person #{track_id}"
            label += f" {conf:.0%}"

            draw_box(frame, x1, y1, x2, y2, label, (0, 255, 0))

        # HUD overlay
        person_count = len(boxes)
        cv2.putText(
            frame, f"People: {person_count} | FPS: {fps:.1f}",
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2,
        )

        cv2.imshow("SPECTER - Human Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
