"""
Calibração interativa — lista unificada no painel direito.
Os 4 primeiros itens ajustam o esquadro de cada mesa.
Os demais ajustam as regiões internas da mesa ativa.
S=salvar  Q=sair  R=resetar  setas=navegar  T=próxima mesa
"""
import cv2
import numpy as np
import json
import os
import sys
from vision.roi_map import TABLE_POSITIONS as DEFAULT_TABLE_POSITIONS, TABLE_KEYS, REGIONS

CONFIG_PATH = "vision/roi_config.json"

# Itens da lista: prefixo "MESA:" = esquadro da mesa, senão = região interna
MESA_ITEMS   = [f"MESA:{tk}" for tk in TABLE_KEYS]
REGION_NAMES = list(REGIONS.keys())
ALL_ITEMS    = MESA_ITEMS + REGION_NAMES          # lista completa do painel

TABLE_COLORS = {
    "top_left":     (0, 255, 255),
    "top_right":    (0, 200, 255),
    "bottom_left":  (0, 255, 200),
    "bottom_right": (0, 180, 255),
}
REGION_COLORS = {
    "title":           (255, 255,   0),
    "pot":             (  0, 255,   0),
    "community_cards": (255, 165,   0),
    "hero_cards":      (  0,   0, 255),
    "action_buttons":  (255,   0, 255),
}

def item_color(item):
    if item.startswith("MESA:"):
        return TABLE_COLORS[item[5:]]
    if item in REGION_COLORS:
        return REGION_COLORS[item]
    if item.startswith("winner_label_"):
        return (50, 255, 50)    # verde-limão — label de vencedor
    if item.startswith("seat_"):
        return (0, 200, 255)
    if item.startswith("bet_"):
        return (180, 180, 0)
    return (160, 160, 160)

def item_label(item):
    if item.startswith("MESA:"):
        return f"[MESA]  {item[5:]}"
    return item


class Calibrator:
    def __init__(self, image_path):
        self.original = cv2.imread(image_path)
        if self.original is None:
            raise FileNotFoundError(f"Não encontrou: {image_path}")

        self.h, self.w = self.original.shape[:2]
        print(f"Imagem: {self.w}x{self.h}")

        self.scale  = min(1.0, 1400 / self.w)
        self.disp_w = int(self.w * self.scale)
        self.disp_h = int(self.h * self.scale)

        cfg = self._load_config()
        self.table_positions = cfg.get("table_positions",
                               {k: list(v) for k, v in DEFAULT_TABLE_POSITIONS.items()})
        self.regions         = cfg.get("regions",
                               {tk: {k: list(v) for k, v in REGIONS.items()}
                                for tk in TABLE_KEYS})

        self.selected_item  = ALL_ITEMS[0]       # item ativo na lista
        self.selected_table = TABLE_KEYS[0]      # mesa ativa (para regiões)
        self.drawing        = False
        self.start_pt       = None
        self.end_pt         = None
        self.scroll         = 0                  # offset de scroll da lista

        self.window = "Calibração  |  S=salvar  Q=sair  R=resetar"
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window, self.disp_w + 300, self.disp_h)
        cv2.setMouseCallback(self.window, self._mouse)

    # ── config ──────────────────────────────────────────────────────────────

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                data = json.load(f)
                print(f"Config carregada de {CONFIG_PATH}")
                # suporte ao formato antigo (só regiões no nível raiz)
                if "table_positions" not in data and "regions" not in data:
                    return {"regions": data}
                return data
        return {}

    def _save_config(self):
        violations = self._validate_all()
        if violations:
            print(f"[CORRIGIDO] Regiões clipadas para dentro do esquadro: {violations}")
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump({
                "calibration_resolution": [self.w, self.h],
                "table_positions": self.table_positions,
                "regions": self.regions,
            }, f, indent=2)
        print(f"Salvo em {CONFIG_PATH} (resolucao={self.w}x{self.h}, {len(TABLE_KEYS)} mesas, {len(REGION_NAMES)} regioes)")

    # ── helpers ─────────────────────────────────────────────────────────────

    def _to_img(self, x, y):
        return int(x / self.scale), int(y / self.scale)

    def _to_disp(self, x, y):
        return int(x * self.scale), int(y * self.scale)

    def _is_mesa_item(self):
        return self.selected_item.startswith("MESA:")

    def _active_mesa_key(self):
        if self._is_mesa_item():
            return self.selected_item[5:]
        return self.selected_table

    # ── mouse ───────────────────────────────────────────────────────────────

    def _mouse(self, event, x, y, flags, param):
        if x > self.disp_w:
            if event == cv2.EVENT_LBUTTONDOWN:
                self._panel_click(y)
            return

        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing  = True
            self.start_pt = (x, y)
            self.end_pt   = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.end_pt = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            self.end_pt  = (x, y)
            self._commit_draw()

    def _panel_click(self, y):
        HEADER_H = 55
        ITEM_H   = 22
        idx = self.scroll + (y - HEADER_H) // ITEM_H
        if 0 <= idx < len(ALL_ITEMS):
            self._select_item(ALL_ITEMS[idx])

    def _select_item(self, item):
        self.selected_item = item
        if item.startswith("MESA:"):
            self.selected_table = item[5:]

    # ── validação ────────────────────────────────────────────────────────────

    def _clip_to_table(self, tk, rx, ry, rw, rh):
        """Clipa uma região para ficar dentro do esquadro da mesa. Retorna (rx,ry,rw,rh) corrigido."""
        _, _, tw, th = self.table_positions[tk]
        rx = max(0, rx)
        ry = max(0, ry)
        rw = min(rw, tw - rx)
        rh = min(rh, th - ry)
        return rx, ry, rw, rh

    def _validate_all(self):
        """Verifica e corrige todas as regiões para ficarem dentro do esquadro correspondente."""
        violations = []
        for tk in TABLE_KEYS:
            _, _, tw, th = self.table_positions[tk]
            for rname, coords in self.regions.get(tk, {}).items():
                rx, ry, rw, rh = coords
                if rx < 0 or ry < 0 or rx + rw > tw or ry + rh > th:
                    violations.append(f"{tk}/{rname}")
                    fixed = self._clip_to_table(tk, rx, ry, rw, rh)
                    self.regions[tk][rname] = list(fixed)
        return violations

    # ── commit do desenho ────────────────────────────────────────────────────

    def _commit_draw(self):
        if not self.start_pt or not self.end_pt:
            return
        x1, y1 = self._to_img(*self.start_pt)
        x2, y2 = self._to_img(*self.end_pt)
        x, y = min(x1, x2), min(y1, y2)
        w, h = abs(x2 - x1), abs(y2 - y1)
        if w < 5 or h < 5:
            return

        if self._is_mesa_item():
            tk = self._active_mesa_key()
            self.table_positions[tk] = [x, y, w, h]
            # Quando o esquadro muda, re-clipa todas as regiões dessa mesa
            for rname, coords in self.regions.get(tk, {}).items():
                self.regions[tk][rname] = list(
                    self._clip_to_table(tk, *coords))
            print(f"[MESA][{tk}] = [{x}, {y}, {w}, {h}]")
        else:
            tk = self.selected_table
            tx, ty, _, _ = self.table_positions[tk]
            rx, ry = x - tx, y - ty
            rx, ry, w, h = self._clip_to_table(tk, rx, ry, w, h)
            if w < 5 or h < 5:
                print(f"[AVISO] Região fora do esquadro de {tk} — ignorada.")
                return
            self.regions[tk][self.selected_item] = [rx, ry, w, h]
            print(f"[REGIÃO][{tk}][{self.selected_item}] = [{rx}, {ry}, {w}, {h}]")

    # ── desenho ─────────────────────────────────────────────────────────────

    def _draw_frame(self):
        canvas = np.zeros((self.disp_h, self.disp_w + 300, 3), dtype=np.uint8)
        img    = cv2.resize(self.original, (self.disp_w, self.disp_h))

        editing_mesa = self._is_mesa_item()
        active_tk    = self._active_mesa_key()

        # Esquadros das mesas
        for tk in TABLE_KEYS:
            tx, ty, tw, th = self.table_positions[tk]
            sx1, sy1 = self._to_disp(tx, ty)
            sx2, sy2 = self._to_disp(tx + tw, ty + th)
            color     = TABLE_COLORS[tk]
            is_active = tk == active_tk

            if editing_mesa and is_active:
                ov = img.copy()
                cv2.rectangle(ov, (sx1, sy1), (sx2, sy2), color, -1)
                cv2.addWeighted(ov, 0.15, img, 0.85, 0, img)
                cv2.rectangle(img, (sx1, sy1), (sx2, sy2), color, 3)
                cv2.putText(img, f"[EDITANDO: {tk}]",
                            (sx1 + 6, sy1 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, color, 2)
            else:
                thickness = 2 if is_active else 1
                cv2.rectangle(img, (sx1, sy1), (sx2, sy2), color, thickness)
                cv2.putText(img, tk, (sx1 + 4, sy1 + 16),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1)

        # Regiões da mesa ativa (quando selecionado um item de região)
        if not editing_mesa:
            tx, ty, _, _ = self.table_positions[active_tk]
            for rname, coords in self.regions.get(active_tk, {}).items():
                rx, ry, rw, rh = coords
                ax1, ay1 = self._to_disp(tx + rx, ty + ry)
                ax2, ay2 = self._to_disp(tx + rx + rw, ty + ry + rh)
                color     = item_color(rname)
                thickness = 2 if rname == self.selected_item else 1
                cv2.rectangle(img, (ax1, ay1), (ax2, ay2), color, thickness)
                cv2.putText(img, rname, (ax1 + 2, ay1 + 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.28, color, 1)

        # Retângulo em progresso
        if self.drawing and self.start_pt and self.end_pt:
            cv2.rectangle(img, self.start_pt, self.end_pt, (255, 255, 255), 1)

        canvas[:, :self.disp_w] = img

        # ── Painel lateral ──────────────────────────────────────────────────
        panel = canvas[:, self.disp_w:]
        panel[:] = (25, 25, 25)

        # Cabeçalho
        sel_color = item_color(self.selected_item)
        cv2.putText(panel, item_label(self.selected_item), (5, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, sel_color, 1)
        cv2.putText(panel, f"mesa ativa: {active_tk}", (5, 38),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.33, TABLE_COLORS[active_tk], 1)

        # Separador
        cv2.line(panel, (0, 48), (299, 48), (60, 60, 60), 1)

        # Lista unificada
        HEADER_H  = 55
        ITEM_H    = 22
        visible   = (self.disp_h - HEADER_H - 50) // ITEM_H

        for i in range(visible):
            idx = self.scroll + i
            if idx >= len(ALL_ITEMS):
                break
            item   = ALL_ITEMS[idx]
            y_pos  = HEADER_H + i * ITEM_H + 14
            color  = item_color(item)
            is_sel = item == self.selected_item

            # Separador visual entre mesas e regiões
            if idx == len(MESA_ITEMS):
                cv2.line(panel, (0, y_pos - 16), (299, y_pos - 16), (60, 60, 60), 1)

            if is_sel:
                cv2.rectangle(panel, (0, y_pos - 14), (299, y_pos + 6), (55, 55, 55), -1)

            cv2.putText(panel, item_label(item), (5, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                        (255, 255, 255) if is_sel else color, 1)

        # Rodapé com atalhos
        foot_y = self.disp_h - 52
        cv2.line(panel, (0, foot_y - 8), (299, foot_y - 8), (50, 50, 50), 1)
        for line in ["S=salvar  Q=sair  R=resetar",
                     "setas cima/baixo = navegar",
                     "T = proxima mesa"]:
            cv2.putText(panel, line, (5, foot_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (90, 90, 90), 1)
            foot_y += 16

        return canvas

    # ── loop principal ───────────────────────────────────────────────────────

    def run(self):
        while True:
            cv2.imshow(self.window, self._draw_frame())
            key = cv2.waitKey(30) & 0xFF

            if key == ord('q'):
                break

            elif key == ord('s'):
                self._save_config()

            elif key == ord('t'):
                idx = (TABLE_KEYS.index(self.selected_table) + 1) % len(TABLE_KEYS)
                self.selected_table = TABLE_KEYS[idx]

            elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
                self.selected_table = TABLE_KEYS[int(chr(key)) - 1]

            elif key == ord('r'):
                if self._is_mesa_item():
                    tk = self._active_mesa_key()
                    self.table_positions[tk] = list(DEFAULT_TABLE_POSITIONS[tk])
                    print(f"Mesa {tk} resetada para padrão.")
                else:
                    tk = self.selected_table
                    self.regions[tk][self.selected_item] = list(REGIONS[self.selected_item])
                    print(f"Região {self.selected_item} resetada para padrão.")

            elif key == 82:  # seta cima
                idx = ALL_ITEMS.index(self.selected_item)
                self._select_item(ALL_ITEMS[max(0, idx - 1)])
                self.scroll = max(0, min(self.scroll, ALL_ITEMS.index(self.selected_item)))

            elif key == 84:  # seta baixo
                idx = ALL_ITEMS.index(self.selected_item)
                self._select_item(ALL_ITEMS[min(len(ALL_ITEMS) - 1, idx + 1)])
                visible = (self.disp_h - 55 - 50) // 22
                sel_pos = ALL_ITEMS.index(self.selected_item) - self.scroll
                if sel_pos >= visible - 1:
                    self.scroll = min(len(ALL_ITEMS) - visible,
                                      ALL_ITEMS.index(self.selected_item) - visible + 2)

        cv2.destroyAllWindows()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "mesa.png"
    Calibrator(path).run()


if __name__ == "__main__":
    main()
