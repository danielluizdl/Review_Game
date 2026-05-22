"""
Calibração interativa — lista unificada no painel direito.
Os 4 primeiros itens ajustam o esquadro de cada mesa.
Os demais ajustam as regiões internas da mesa ativa.
S=salvar  Q=sair  R=resetar  setas=navegar  T=próxima mesa
Espaço=próximo frame  ,=frame anterior  (somente com vídeo)
"""
import cv2
import numpy as np
import json
import os
import sys
from pathlib import Path
from vision.roi_map import TABLE_POSITIONS as DEFAULT_TABLE_POSITIONS, TABLE_KEYS, REGIONS

_VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov"}

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
    "pot_total":       (  0, 255,   0),   # verde — pot acumulado da mão
    "pot_ante":        (  0, 200, 100),   # verde-água — pot de antes (pré-blinds)
    "community_cards": (255, 165,   0),
    "hero_cards":      (  0,   0, 255),
    "action_buttons":  (255,   0, 255),
}

def item_color(item):
    if item.startswith("MESA:"):
        return TABLE_COLORS[item[5:]]
    if item in REGION_COLORS:
        return REGION_COLORS[item]
    if item.startswith("dealer_seat_"):
        return (0, 140, 255)    # laranja — botão dealer
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
        self._cap         = None
        self.frame_idx    = 0
        self.total_frames = 1
        self._fps         = 1.0

        if Path(image_path).suffix.lower() in _VIDEO_EXTS:
            self._cap = cv2.VideoCapture(image_path)
            if not self._cap.isOpened():
                raise FileNotFoundError(f"Não abriu o vídeo: {image_path}")
            self.total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self._fps         = self._cap.get(cv2.CAP_PROP_FPS) or 30.0
            self.original     = self._read_video_frame(0)
            if self.original is None:
                raise RuntimeError("Não conseguiu ler o primeiro frame do vídeo")
            print(f"Vídeo: {self.total_frames} frames  {self._fps:.0f}fps")
        else:
            self.original = cv2.imread(image_path)
            if self.original is None:
                raise FileNotFoundError(f"Não encontrou: {image_path}")

        self.h, self.w = self.original.shape[:2]
        print(f"Resolução: {self.w}x{self.h}")

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
        self.offset_mode    = False              # O=mover todas as mesas juntas

        self.window = "Calibração  |  S=salvar  Q=sair  R=resetar"
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.window, self.disp_w + 300, self.disp_h)
        cv2.moveWindow(self.window, 0, 0)
        cv2.setMouseCallback(self.window, self._mouse)

    # ── navegação de vídeo ──────────────────────────────────────────────────

    def _read_video_frame(self, idx: int):
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = self._cap.read()
        return frame if ret else None

    def _seek(self, delta: int):
        if self._cap is None:
            return
        new_idx = max(0, min(self.total_frames - 1, self.frame_idx + delta))
        if new_idx == self.frame_idx:
            return
        self.frame_idx = new_idx
        frame = self._read_video_frame(new_idx)
        if frame is not None:
            self.original = frame

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
        # Faz backup antes de sobrescrever
        backup_path = CONFIG_PATH.replace(".json", "_backup.json")
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                backup_data = f.read()
            with open(backup_path, "w") as f:
                f.write(backup_data)
        # Preserva campos extras do config (ex: ante_config) e atualiza só o que mudou
        try:
            with open(CONFIG_PATH) as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            existing = {}
        existing.update({
            "calibration_resolution": [self.w, self.h],
            "table_positions":        self.table_positions,
            "regions":                self.regions,
        })
        with open(CONFIG_PATH, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"Salvo em {CONFIG_PATH}  |  backup em {backup_path}")

    def _auto_detect_tables(self):
        """
        Detecta automaticamente as 4 mesas por perfil de escuridão.
        Encontra o divisor vertical e horizontal mais escuros perto do centro,
        depois força simetria perfeita (4 quadrantes iguais).
        """
        gray = cv2.cvtColor(self.original, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Divisor vertical: coluna mais escura ±80px ao redor do centro
        cx, sr = w // 2, 80
        col_mean = np.mean(gray, axis=0)
        x_split  = cx - sr + int(np.argmin(col_mean[cx - sr: cx + sr]))

        # Divisor horizontal: linha mais escura ±80px ao redor do centro
        cy = h // 2
        row_mean = np.mean(gray, axis=1)
        y_split  = cy - sr + int(np.argmin(row_mean[cy - sr: cy + sr]))

        # Detecta topo da barra de tarefas (std baixo = conteúdo uniforme)
        taskbar_top = h
        for yb in range(h - 1, h * 2 // 3, -1):
            if np.std(gray[yb, :].astype(float)) > 15:
                taskbar_top = yb + 1
                break

        # Força simetria: mesas iguais dos dois lados do divisor
        tw = x_split                    # largura da mesa esquerda
        th = y_split                    # altura da mesa de cima
        bh = taskbar_top - y_split      # altura da mesa de baixo

        self.table_positions = {
            "top_left":     [0,       0,       tw, th],
            "top_right":    [x_split, 0,       w - x_split, th],
            "bottom_left":  [0,       y_split, tw, bh],
            "bottom_right": [x_split, y_split, w - x_split, bh],
        }
        print(f"[AUTO] x={x_split}  y={y_split}  taskbar={taskbar_top}")
        for k, v in self.table_positions.items():
            print(f"  {k}: {v}")

    def _restore_backup(self):
        backup_path = CONFIG_PATH.replace(".json", "_backup.json")
        if not os.path.exists(backup_path):
            print("[BACKUP] Nenhum backup encontrado.")
            return
        with open(backup_path) as f:
            data = json.load(f)
        self.table_positions = data.get("table_positions", self.table_positions)
        self.regions         = data.get("regions",         self.regions)
        print(f"[BACKUP] Restaurado de {backup_path}")

    def _copy_to_all_tables(self):
        """Copia as regiões internas da mesa ativa para todas as outras mesas."""
        src = self._active_mesa_key()
        src_regions = self.regions.get(src, {})
        for tk in TABLE_KEYS:
            if tk == src:
                continue
            # Preserva regiões exclusivas da mesa destino (ex: dealer_seat_N já calibradas)
            # mas sobrescreve todas as regiões de layout (seat, bet, pot, etc.)
            self.regions[tk].update({k: list(v) for k, v in src_regions.items()})
            # Reclipa para garantir que ficam dentro do esquadro destino
            for rname in list(src_regions.keys()):
                self.regions[tk][rname] = list(
                    self._clip_to_table(tk, *self.regions[tk][rname]))
        print(f"[COPIAR] Regiões de '{src}' copiadas para {[tk for tk in TABLE_KEYS if tk != src]}")

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
                self._panel_click(x - self.disp_w, y)
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

    def _panel_click(self, x, y):
        # Scrollbar: últimos 12px do painel
        if x >= 288:
            self._scrollbar_click(y)
            return
        HEADER_H = 55
        ITEM_H   = 22
        idx = self.scroll + (y - HEADER_H) // ITEM_H
        if 0 <= idx < len(ALL_ITEMS):
            self._select_item(ALL_ITEMS[idx])

    def _scrollbar_click(self, y):
        HEADER_H = 55
        FOOTER_H = 76
        track_h  = self.disp_h - HEADER_H - FOOTER_H
        if track_h <= 0:
            return
        visible  = self._visible_count()
        max_scroll = max(0, len(ALL_ITEMS) - visible)
        ratio    = max(0.0, min(1.0, (y - HEADER_H) / track_h))
        self.scroll = int(ratio * max_scroll)

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

        # Modo offset: move todas as regiões internas da mesa ativa
        if self.offset_mode:
            dx = x2 - x1
            dy = y2 - y1
            if abs(dx) > 1 or abs(dy) > 1:
                tk = self._active_mesa_key()
                for rname, coords in self.regions.get(tk, {}).items():
                    rx, ry, rw, rh = coords
                    self.regions[tk][rname] = list(
                        self._clip_to_table(tk, rx + dx, ry + dy, rw, rh))
                print(f"[OFFSET][{tk}] dx={dx}, dy={dy} aplicado em todas as regiões.")
            self.offset_mode = False
            return

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
        visible   = self._visible_count()

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

        # Indicador de modo offset
        if self.offset_mode:
            tk = self._active_mesa_key()
            cv2.rectangle(panel, (0, 0), (299, 26), (0, 100, 200), -1)
            cv2.putText(panel, f"OFFSET: arraste p/ mover [{tk}]",
                        (4, 17), cv2.FONT_HERSHEY_SIMPLEX, 0.33, (255, 255, 255), 1)

        # Indicador de frame (somente vídeo)
        if self._cap is not None:
            ts = self.frame_idx / self._fps
            m, s = divmod(int(ts), 60)
            info = f"Frame {self.frame_idx + 1}/{self.total_frames}  ({m:02d}:{s:02d})"
            cv2.rectangle(panel, (0, self.disp_h - 72), (299, self.disp_h - 58), (40, 40, 60), -1)
            cv2.putText(panel, info, (5, self.disp_h - 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.33, (160, 200, 255), 1)

        # Scrollbar vertical (últimos 10px do painel)
        HEADER_H = 55
        FOOTER_H = 76
        track_h  = self.disp_h - HEADER_H - FOOTER_H
        visible  = self._visible_count()
        max_scroll = max(1, len(ALL_ITEMS) - visible)
        thumb_h  = max(20, int(track_h * visible / len(ALL_ITEMS)))
        thumb_y  = HEADER_H + int((self.scroll / max_scroll) * (track_h - thumb_h))
        cv2.rectangle(panel, (288, HEADER_H), (298, HEADER_H + track_h), (40, 40, 40), -1)
        cv2.rectangle(panel, (289, thumb_y),  (297, thumb_y + thumb_h),  (110, 110, 140), -1)

        # Rodapé com atalhos
        foot_y = self.disp_h - 68
        cv2.line(panel, (0, foot_y - 4), (287, foot_y - 4), (50, 50, 50), 1)
        lines = ["S=salvar  Q=sair  R=resetar  O=offset",
                 "A=detectar mesas automaticamente",
                 "C=copiar mesa p/ todas  B=backup",
                 "Setas=navegar  T=proxima mesa"]
        if self._cap is not None:
            lines.append("Espaco=+1s  ,=-1s")
        for line in lines:
            cv2.putText(panel, line, (5, foot_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (90, 90, 90), 1)
            foot_y += 16

        return canvas

    # ── loop principal ───────────────────────────────────────────────────────

    def _visible_count(self):
        HEADER_H = 55
        FOOTER_H = 76  # espaço reservado pro rodapé
        return max(1, (self.disp_h - HEADER_H - FOOTER_H) // 22)

    def run(self):
        while True:
            cv2.imshow(self.window, self._draw_frame())
            raw = cv2.waitKey(30)
            if raw == -1:
                continue
            key = raw & 0xFF
            # Setas: Linux retorna 82/84; Windows retorna 2490368/2621440
            is_up   = (key == 82)  or (raw == 2490368)
            is_down = (key == 84)  or (raw == 2621440)

            if key == ord('q'):
                break

            elif key == ord('s'):
                self._save_config()

            elif key == ord('t'):
                idx = (TABLE_KEYS.index(self.selected_table) + 1) % len(TABLE_KEYS)
                self.selected_table = TABLE_KEYS[idx]

            elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
                self.selected_table = TABLE_KEYS[int(chr(key)) - 1]

            elif key == ord('a'):
                self._auto_detect_tables()

            elif key == ord('o'):
                self.offset_mode = not self.offset_mode
                print("[OFFSET MODE]" if self.offset_mode else "[OFFSET MODE desativado]")

            elif key == ord('c'):
                self._copy_to_all_tables()

            elif key == ord('b'):
                self._restore_backup()

            elif key == ord('r'):
                if self._is_mesa_item():
                    tk = self._active_mesa_key()
                    self.table_positions[tk] = list(DEFAULT_TABLE_POSITIONS[tk])
                    print(f"Mesa {tk} resetada para padrão.")
                else:
                    tk = self.selected_table
                    self.regions[tk][self.selected_item] = list(REGIONS[self.selected_item])
                    print(f"Região {self.selected_item} resetada para padrão.")

            elif is_up:
                idx = ALL_ITEMS.index(self.selected_item)
                self._select_item(ALL_ITEMS[max(0, idx - 1)])
                self.scroll = max(0, min(self.scroll, ALL_ITEMS.index(self.selected_item)))

            elif is_down:
                idx = ALL_ITEMS.index(self.selected_item)
                self._select_item(ALL_ITEMS[min(len(ALL_ITEMS) - 1, idx + 1)])
                visible = self._visible_count()
                if ALL_ITEMS.index(self.selected_item) - self.scroll >= visible - 1:
                    self.scroll = min(len(ALL_ITEMS) - visible,
                                      ALL_ITEMS.index(self.selected_item) - visible + 2)

            elif key == 32:   # Espaço → +1 segundo
                self._seek(int(self._fps))

            elif key == 44:   # vírgula → -1 segundo
                self._seek(-int(self._fps))

        if self._cap is not None:
            self._cap.release()
        cv2.destroyAllWindows()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "mesa.png"
    try:
        Calibrator(path).run()
    except (FileNotFoundError, RuntimeError) as e:
        print(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
