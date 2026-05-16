"""
Testa OCR nas regiões calibradas de um screenshot.
Uso: python test_ocr.py <screenshot.png>
"""
import sys
import cv2
import json
import os

CONFIG_PATH = "vision/roi_config.json"


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def scale_coords(coords, sx, sy):
    x, y, w, h = coords
    return int(round(x * sx)), int(round(y * sy)), int(round(w * sx)), int(round(h * sy))


def get_region(frame, table_pos, region_coords, sx=1.0, sy=1.0):
    tx, ty, tw, th = scale_coords(table_pos, sx, sy)
    rx, ry, rw, rh = scale_coords(region_coords, sx, sy)
    x1, y1 = tx + rx, ty + ry
    x2, y2 = x1 + rw, y1 + rh
    return frame[y1:y2, x1:x2]


def save_crop(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cv2.imwrite(path, img)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "mesa.png"
    frame = cv2.imread(path)
    if frame is None:
        print(f"Erro: não encontrou '{path}'")
        sys.exit(1)

    h, w = frame.shape[:2]
    print(f"Frame: {w}x{h}")

    cfg = load_config()
    table_positions = cfg["table_positions"]
    regions         = cfg["regions"]

    calib_w, calib_h = cfg.get("calibration_resolution", [w, h])
    sx = w / calib_w
    sy = h / calib_h
    if abs(sx - 1.0) > 0.001 or abs(sy - 1.0) > 0.001:
        print(f"Escalonando ROIs: {calib_w}x{calib_h} → {w}x{h} (sx={sx:.3f}, sy={sy:.3f})")

    # Salva crops das regiões para inspeção visual antes de rodar OCR
    print("\nSalvando crops em data/crops/ para você inspecionar...")
    for tk, tpos in table_positions.items():
        for rname, rcoords in regions[tk].items():
            crop = get_region(frame, tpos, rcoords, sx, sy)
            if crop.size == 0:
                continue
            save_crop(crop, f"data/crops/{tk}/{rname}.png")

    print("Crops salvos. Verifique a pasta data/crops/ e confirme que as imagens")
    print("estão capturando as regiões certas antes de rodar o OCR.")
    print()

    # Salva também os crops pré-processados para comparação
    from vision.ocr_reader import _preprocess_number, _preprocess_name
    print("Salvando crops pré-processados em data/crops_processed/ ...")
    for tk, tpos in table_positions.items():
        for rname, rcoords in regions[tk].items():
            crop = get_region(frame, tpos, rcoords, sx, sy)
            if crop.size == 0:
                continue
            if rname in ("pot", "title") or rname.startswith("seat_") or rname.startswith("bet_"):
                proc = _preprocess_number(crop)
            else:
                proc = _preprocess_name(crop)
            save_crop(proc, f"data/crops_processed/{tk}/{rname}.png")

    # Roda OCR nas regiões principais
    from vision.ocr_reader import read_stack, read_pot, read_player_name, read_table_id

    print("\n" + "="*60)
    for tk, tpos in table_positions.items():
        print(f"\n[{tk}]")

        title_crop = get_region(frame, tpos, regions[tk]["title"], sx, sy)
        print(f"  {'title':<20} → '{read_table_id(title_crop)}'")

        pot_crop = get_region(frame, tpos, regions[tk]["pot"], sx, sy)
        print(f"  {'pot':<20} → {read_pot(pot_crop)} BB")

        for rname in [f"seat_{i}" for i in range(1, 9)]:
            if rname not in regions[tk]:
                continue
            crop = get_region(frame, tpos, regions[tk][rname], sx, sy)
            if crop.size == 0:
                continue
            name  = read_player_name(crop)
            stack = read_stack(crop)
            print(f"  {rname:<20} → nome='{name}'  stack={stack} BB")
    print("="*60)


if __name__ == "__main__":
    main()
