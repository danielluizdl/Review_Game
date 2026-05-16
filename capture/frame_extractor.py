"""
Extrai frames de um arquivo MP4 em intervalos regulares ou por mudança de cena.
"""
import cv2
import os


def extract_frames(video_path: str, output_dir: str, interval_sec: float = 0.5):
    """
    Extrai um frame a cada `interval_sec` segundos do vídeo.
    Salva como PNG numerado em output_dir.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Não foi possível abrir: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    interval_frames = max(1, int(fps * interval_sec))

    os.makedirs(output_dir, exist_ok=True)

    saved = 0
    frame_idx = 0

    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            break

        out_path = os.path.join(output_dir, f"frame_{frame_idx:08d}.png")
        cv2.imwrite(out_path, frame)
        saved += 1

        frame_idx += interval_frames
        if frame_idx >= total_frames:
            break

    cap.release()
    print(f"Extraídos {saved} frames de '{video_path}' → '{output_dir}'")
    return saved


def get_video_info(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    info = {
        "width":  int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps":    cap.get(cv2.CAP_PROP_FPS),
        "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    info["duration_sec"] = info["frames"] / info["fps"] if info["fps"] else 0
    cap.release()
    return info
