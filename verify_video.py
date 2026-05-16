"""
Verifica a captação em N frames espalhados pelo vídeo.
Salva imagens com o texto detectado desenhado sobre o frame.
Uso: python verify_video.py cortado.mp4 [N=10]
"""
import sys
import cv2
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CONFIG_PATH = "vision/roi_config.json"
OUT_DIR     = "data/verify"

# Fontes do Windows com suporte a caracteres CJK (chinês/japonês/coreano)
_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",    # Microsoft YaHei
    r"C:\Windows\Fonts\simsun.ttc",  # SimSun
    r"C:\Windows\Fonts\simhei.ttf",  # SimHei
    r"C:\Windows\Fonts\arial.ttf",   # fallback sem CJK
]

def _load_font(size):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

_FONT_SM = _load_font(13)
_FONT_MD = _load_font(16)


def _put_text(draw, text, xy, color, font):
    """Desenha texto com suporte a Unicode via Pillow."""
    x, y = xy
    draw.text((x + 1, y + 1), text, fill=(0, 0, 0), font=font)  # sombra
    draw.text((x, y), text, fill=color, font=font)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def draw_results(frame, cfg, results, sx, sy):
    """Anota o frame com os dados detectados usando Pillow (suporta CJK)."""
    # BGR→RGB para Pillow
    img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw    = ImageDraw.Draw(img_pil)

    table_positions = cfg["table_positions"]
    regions         = cfg["regions"]

    TABLE_COLORS = {
        "top_left":     (0, 255, 255),
        "top_right":    (0, 200, 255),
        "bottom_left":  (0, 255, 200),
        "bottom_right": (0, 180, 255),
    }

    for tk, data in results.items():
        tpos  = table_positions[tk]
        color = TABLE_COLORS[tk]
        tx = int(round(tpos[0] * sx)); ty = int(round(tpos[1] * sy))
        tw = int(round(tpos[2] * sx)); th = int(round(tpos[3] * sy))

        draw.rectangle([(tx, ty), (tx+tw, ty+th)], outline=color, width=2)
        _put_text(draw, f"{data['table_id']} | {data['blinds']} | {data['game_type']}  pot={data['pot']} BB",
                  (tx+6, ty+4), color, _FONT_MD)

        regs = regions[tk]
        for sk, info in data["seats"].items():
            if sk not in regs:
                continue
            rx, ry, rw, rh = regs[sk]
            x1 = tx + int(round(rx * sx))
            y1 = ty + int(round(ry * sy))
            x2 = x1 + int(round(rw * sx))
            y2 = y1 + int(round(rh * sy))
            draw.rectangle([(x1, y1), (x2, y2)], outline=(0, 255, 0), width=1)
            _put_text(draw, f"{info['name']} {info['stack']}BB",
                      (x1+2, y1+1), (0, 255, 0), _FONT_SM)

    # RGB→BGR para salvar com OpenCV
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)


def main():
    import os
    from vision.ocr_reader import read_table

    video_path = sys.argv[1] if len(sys.argv) > 1 else "cortado.mp4"
    n_samples  = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    cfg = load_config()
    calib_w, calib_h = cfg.get("calibration_resolution", [1920, 1080])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Erro: nao abriu '{video_path}'")
        sys.exit(1)

    fps         = cap.get(cv2.CAP_PROP_FPS)
    total       = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fw          = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    fh          = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration    = total / fps
    sx, sy      = fw / calib_w, fh / calib_h

    print(f"Video: {fw}x{fh}  {fps:.0f}fps  {duration/60:.1f}min")
    print(f"Escala: sx={sx:.3f} sy={sy:.3f}")
    print(f"Amostrando {n_samples} frames...\n")

    os.makedirs(OUT_DIR, exist_ok=True)

    # Frames igualmente espaçados (evita início e fim)
    margin = int(fps * 10)  # 10s de margem
    positions = np.linspace(margin, total - margin, n_samples, dtype=int)

    for i, pos in enumerate(positions, 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
        ret, frame = cap.read()
        if not ret:
            continue

        ts = pos / fps
        print(f"[{i}/{n_samples}] t={ts/60:.1f}min ({ts:.0f}s)  ", end="", flush=True)

        results = {}
        for tk, tpos in cfg["table_positions"].items():
            results[tk] = read_table(frame, tpos, cfg["regions"][tk], sx, sy)

        # Resumo no terminal
        for tk, data in results.items():
            print(f"{tk[:2].upper()}{tk[-1].upper()}={data['table_id']} pot={data['pot']}", end="  ")
        print()

        # Salva imagem com anotações
        annotated = draw_results(frame, cfg, results, sx, sy)
        out_path  = os.path.join(OUT_DIR, f"verify_{i:02d}_{int(ts):04d}s.png")
        cv2.imwrite(out_path, annotated)

    cap.release()
    print(f"\nImagens salvas em {OUT_DIR}/")
    print("Abra as imagens e confirme se os nomes e stacks estao corretos.")


if __name__ == "__main__":
    main()
