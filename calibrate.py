"""
Ferramenta de calibração: mostra as regiões mapeadas sobre um screenshot real.
Uso: python calibrate.py <caminho_do_screenshot>
"""
import sys
import cv2
import numpy as np
from vision.roi_map import TABLE_POSITIONS, TABLE_KEYS, REGIONS, get_table_roi, get_region

COLORS = {
    "title":           (255, 255,   0),
    "pot":             (  0, 255,   0),
    "community_cards": (255, 165,   0),
    "hero_cards":      (  0,   0, 255),
    "action_buttons":  (255,   0, 255),
}
SEAT_COLOR   = (0, 200, 255)
BET_COLOR    = (180, 180, 0)


def draw_rois(frame):
    vis = frame.copy()

    for table_key in TABLE_KEYS:
        tx, ty, tw, th = TABLE_POSITIONS[table_key]
        cv2.rectangle(vis, (tx, ty), (tx+tw, ty+th), (200, 200, 200), 2)
        cv2.putText(vis, table_key, (tx+5, ty+20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        for region_key, (rx, ry, rw, rh) in REGIONS.items():
            ax, ay = tx + rx, ty + ry
            if region_key.startswith("seat_"):
                color = SEAT_COLOR
            elif region_key.startswith("bet_"):
                color = BET_COLOR
            else:
                color = COLORS.get(region_key, (128, 128, 128))

            cv2.rectangle(vis, (ax, ay), (ax+rw, ay+rh), color, 1)
            cv2.putText(vis, region_key, (ax+2, ay+12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.3, color, 1)

    return vis


def main():
    if len(sys.argv) < 2:
        print("Uso: python calibrate.py <screenshot.png>")
        sys.exit(1)

    path = sys.argv[1]
    frame = cv2.imread(path)
    if frame is None:
        print(f"Erro: não conseguiu abrir '{path}'")
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"Imagem carregada: {w}x{h}")

    vis = draw_rois(frame)

    # Redimensiona pra caber na tela se for muito grande
    scale = min(1.0, 1400 / w)
    if scale < 1.0:
        vis = cv2.resize(vis, (int(w*scale), int(h*scale)))

    cv2.imshow("Calibracao - pressione Q para sair", vis)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

    out = path.replace(".png", "_calibrated.png").replace(".jpg", "_calibrated.jpg")
    cv2.imwrite(out, vis)
    print(f"Salvo: {out}")


if __name__ == "__main__":
    main()
