"""
Desenha as ROIs calibradas sobre um frame para inspeção visual.
Uso: python visualize_rois.py <frame.png>
"""
import sys
import cv2
import json
import numpy as np

CONFIG_PATH = "vision/roi_config.json"

COLORS = {
    "title":          (0,   255, 255),  # amarelo
    "pot":            (0,   200, 255),  # laranja
    "community_cards":(255, 200,   0),  # azul claro
    "hero_cards":     (200,   0, 255),  # roxo
    "action_buttons": (150, 150, 150),  # cinza
}
SEAT_COLOR   = (0, 255, 0)    # verde
BET_COLOR    = (0, 120, 255)  # vermelho-alaranjado
TABLE_COLOR  = (255, 255, 255) # branco


def scale_coords(coords, sx, sy):
    x, y, w, h = coords
    return int(round(x*sx)), int(round(y*sy)), int(round(w*sx)), int(round(h*sy))


def draw_rois(frame, cfg, sx, sy, table_keys=None):
    out = frame.copy()
    table_positions = cfg["table_positions"]
    regions         = cfg["regions"]

    if table_keys is None:
        table_keys = list(table_positions.keys())

    for tk in table_keys:
        tpos = table_positions[tk]
        tx, ty, tw, th = scale_coords(tpos, sx, sy)

        # Borda da mesa
        cv2.rectangle(out, (tx, ty), (tx+tw, ty+th), TABLE_COLOR, 1)
        cv2.putText(out, tk, (tx+4, ty+14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, TABLE_COLOR, 1)

        for rname, rcoords in regions[tk].items():
            rx, ry, rw, rh = scale_coords(rcoords, sx, sy)
            x1, y1 = tx+rx, ty+ry
            x2, y2 = x1+rw, y1+rh

            if rname.startswith("seat_"):
                color = SEAT_COLOR
            elif rname.startswith("bet_"):
                color = BET_COLOR
            else:
                color = COLORS.get(rname, (180, 180, 180))

            cv2.rectangle(out, (x1, y1), (x2, y2), color, 1)
            label = rname.replace("seat_", "s").replace("bet_seat_", "b")
            cv2.putText(out, label, (x1+2, y1+11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "frame_inicio_30s.png"
    frame = cv2.imread(path)
    if frame is None:
        print(f"Erro: nao encontrou '{path}'")
        sys.exit(1)

    h, w = frame.shape[:2]
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx = w / calib_w
    sy = h / calib_h
    print(f"Frame: {w}x{h}  |  Calibragem: {calib_w}x{calib_h}  |  escala: sx={sx:.3f} sy={sy:.3f}")

    out = draw_rois(frame, cfg, sx, sy)
    out_path = path.replace(".png", "_rois.png")
    cv2.imwrite(out_path, out)
    print(f"Salvo: {out_path}")

    # Mostra na tela (pressione qualquer tecla para fechar)
    display = cv2.resize(out, (1280, 720))
    cv2.imshow("ROIs sobre o frame (qualquer tecla para fechar)", display)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
