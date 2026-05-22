"""
Calibração das regiões do botão de dealer (D) para cada assento de cada mesa.

Posiciona 8 regiões dealer_seat_N por mesa — o OCR verifica qual contém o "D"
para determinar o BTN diretamente da imagem (sem inferir pelas apostas).

Uso:
  python calibrate_dealer.py frame.png          # screenshot estático
  python calibrate_dealer.py video.mp4          # navegação frame a frame

Controles:
  Arrastar mouse           = define região do seat ativo
  ← → ↑ ↓  (ou W A S D)  = move ±1 px
  Shift  +  ← → ↑ ↓       = redimensiona ±1 px  (codigos 87 65 83 68 maiúsc.)
  N / B                    = próximo / anterior seat (ou clique no painel)
  T  /  1 2 3 4            = alterna mesa ativa
  Espaço  /  .             = avança 30 frames  (vídeo)
  ,                        = recua 30 frames   (vídeo)
  S                        = salva em roi_config.json  (preserva todos os campos)
  Q                        = sai sem salvar
"""
import cv2
import json
import numpy as np
import os
import sys

CONFIG_PATH = "vision/roi_config.json"
TABLE_KEYS  = ["top_left", "top_right", "bottom_left", "bottom_right"]
N_SEATS     = 8
SEAT_KEYS   = [f"seat_{i}" for i in range(1, N_SEATS + 1)]
DEALER_KEYS = [f"dealer_seat_{i}" for i in range(1, N_SEATS + 1)]
STEP_FRAMES = 30    # frames por avanço no vídeo

TABLE_COLORS = {
    "top_left":     (0, 255, 255),
    "top_right":    (0, 200, 255),
    "bottom_left":  (0, 255, 200),
    "bottom_right": (0, 180, 255),
}
COLOR_ACTIVE   = (0, 140, 255)   # laranja — seat selecionado
COLOR_INACTIVE = (80, 120, 200)  # azul-escuro — outros seats


class DealerCalibrator:
    """Calibrador interativo para as regiões do botão de dealer."""

    def __init__(self, source: str):
        with open(CONFIG_PATH) as f:
            self._cfg = json.load(f)

        self.calib_w, self.calib_h = self._cfg.get("calibration_resolution", [1920, 1080])
        self.table_positions        = self._cfg["table_positions"]

        # Copia profunda das regiões (não modifica o cfg original até salvar)
        self.regions = {tk: dict(self._cfg["regions"].get(tk, {}))
                        for tk in TABLE_KEYS}
        self._init_defaults()

        self.active_tk   = TABLE_KEYS[0]
        self.active_seat = 0      # índice 0-7 em SEAT_KEYS
        self.drawing     = False
        self.start_pt: tuple | None = None
        self.end_pt:   tuple | None = None

        self._setup_source(source)

        self._current_frame = self._read_frame()
        fh, fw = self._current_frame.shape[:2]

        # Escala de exibição — cabe em 1380 × 900
        self.scale  = min(1.0, 1380 / fw, 900 / fh)
        self.disp_w = int(fw * self.scale)
        self.disp_h = int(fh * self.scale)

        self._win = "Dealer Button  |  S=salvar  Q=sair  N/B=seat  T=mesa  Espaco=frame"
        cv2.namedWindow(self._win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self._win, self.disp_w + 270, self.disp_h)
        cv2.setMouseCallback(self._win, self._on_mouse)

    # ── configuração da fonte de imagens ─────────────────────────────────────

    def _setup_source(self, source: str):
        ext = os.path.splitext(source)[1].lower()
        if ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            self._cap    = cv2.VideoCapture(source)
            if not self._cap.isOpened():
                raise FileNotFoundError(f"Não abriu vídeo: {source}")
            self._fps    = max(1.0, self._cap.get(cv2.CAP_PROP_FPS))
            self._total  = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
            self._fidx   = 0
            self._is_vid = True
        else:
            img = cv2.imread(source)
            if img is None:
                raise FileNotFoundError(f"Não abriu imagem: {source}")
            self._static = img
            self._is_vid = False
            self._total  = 1
            self._fidx   = 0

    def _read_frame(self) -> np.ndarray:
        if not self._is_vid:
            return self._static.copy()
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._fidx)
        ret, frame = self._cap.read()
        return frame if (ret and frame is not None) else \
               np.zeros((self.calib_h, self.calib_w, 3), dtype=np.uint8)

    def _advance(self, step: int):
        if not self._is_vid:
            return
        self._fidx = max(0, min(self._total - 1, self._fidx + step))
        self._current_frame = self._read_frame()

    # ── posições padrão ──────────────────────────────────────────────────────

    def _init_defaults(self):
        """
        Inicializa dealer_seat_N que ainda não existem.
        Usa bet_seat_N como âncora (ligeiramente acima), caindo em seat_N se necessário.
        """
        for tk in TABLE_KEYS:
            regs = self.regions[tk]
            for i in range(1, N_SEATS + 1):
                dk = f"dealer_seat_{i}"
                if dk in regs:
                    continue
                bk, sk = f"bet_seat_{i}", f"seat_{i}"
                if bk in regs:
                    bx, by, bw, bh = regs[bk]
                    regs[dk] = [bx, max(0, by - 28), 28, 22]
                elif sk in regs:
                    sx, sy, sw, sh = regs[sk]
                    regs[dk] = [sx + sw // 2 - 14, max(0, sy - 28), 28, 22]
                else:
                    regs[dk] = [10, 10, 28, 22]

    # ── helpers de coordenadas ───────────────────────────────────────────────

    def _disp_to_calib(self, dx: int, dy: int) -> tuple[int, int]:
        """Converte coordenadas de display → coordenadas de calibração."""
        fh, fw = self._current_frame.shape[:2]
        ix  = dx / self.scale
        iy  = dy / self.scale
        cx  = int(ix * self.calib_w / fw)
        cy  = int(iy * self.calib_h / fh)
        return cx, cy

    def _calib_to_disp(self, cx: int, cy: int) -> tuple[int, int]:
        """Converte coordenadas de calibração → coordenadas de display."""
        fh, fw = self._current_frame.shape[:2]
        ix = cx * fw / self.calib_w
        iy = cy * fh / self.calib_h
        return int(ix * self.scale), int(iy * self.scale)

    def _active_key(self) -> str:
        return DEALER_KEYS[self.active_seat]

    # ── mouse ────────────────────────────────────────────────────────────────

    def _on_mouse(self, event, x, y, flags, param):
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
            self.drawing  = False
            self.end_pt   = (x, y)
            self._commit_draw()

    def _panel_click(self, y: int):
        HEADER = 80
        ITEM_H = 22
        idx = (y - HEADER) // ITEM_H
        if 0 <= idx < N_SEATS:
            self.active_seat = idx

    def _commit_draw(self):
        if not self.start_pt or not self.end_pt:
            return
        cx1, cy1 = self._disp_to_calib(*self.start_pt)
        cx2, cy2 = self._disp_to_calib(*self.end_pt)
        tx, ty, tw, th = self.table_positions[self.active_tk]
        rx  = min(cx1, cx2) - tx
        ry  = min(cy1, cy2) - ty
        rw  = abs(cx2 - cx1)
        rh  = abs(cy2 - cy1)
        if rw < 4 or rh < 4:
            return
        rx = max(0, min(rx, tw - max(rw, 1)))
        ry = max(0, min(ry, th - max(rh, 1)))
        dk = self._active_key()
        self.regions[self.active_tk][dk] = [rx, ry, rw, rh]
        print(f"[{self.active_tk}][{dk}] = [{rx}, {ry}, {rw}, {rh}]")

    # ── ajuste por teclas ────────────────────────────────────────────────────

    def _move(self, dx: int, dy: int):
        r = self.regions[self.active_tk][self._active_key()]
        r[0] += dx
        r[1] += dy

    def _resize(self, dw: int, dh: int):
        r = self.regions[self.active_tk][self._active_key()]
        r[2] = max(4, r[2] + dw)
        r[3] = max(4, r[3] + dh)

    # ── salvar ───────────────────────────────────────────────────────────────

    def _save(self):
        for tk in TABLE_KEYS:
            for dk in DEALER_KEYS:
                self._cfg["regions"][tk][dk] = self.regions[tk][dk]
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._cfg, f, indent=2)
        print(f"Salvo: {CONFIG_PATH}  "
              f"({N_SEATS * len(TABLE_KEYS)} regiões dealer atualizadas)")

    # ── renderização ──────────────────────────────────────────────────────────

    def _draw(self) -> np.ndarray:
        frame = self._current_frame
        fh, fw = frame.shape[:2]
        img   = cv2.resize(frame, (self.disp_w, self.disp_h))

        # Esquadros de todas as mesas
        for tk in TABLE_KEYS:
            tx, ty, tw, th = self.table_positions[tk]
            p1 = self._calib_to_disp(tx, ty)
            p2 = self._calib_to_disp(tx + tw, ty + th)
            col   = TABLE_COLORS[tk]
            thick = 2 if tk == self.active_tk else 1
            cv2.rectangle(img, p1, p2, col, thick)
            cv2.putText(img, tk, (p1[0] + 4, p1[1] + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, col, 1)

        # Todas as 8 regiões dealer da mesa ativa
        tk = self.active_tk
        tx, ty, _, _ = self.table_positions[tk]
        for i, dk in enumerate(DEALER_KEYS):
            r = self.regions[tk].get(dk)
            if not r:
                continue
            rx, ry, rw, rh = r
            p1 = self._calib_to_disp(tx + rx,      ty + ry)
            p2 = self._calib_to_disp(tx + rx + rw, ty + ry + rh)
            is_sel = (i == self.active_seat)
            col    = COLOR_ACTIVE if is_sel else COLOR_INACTIVE
            if is_sel:
                overlay = img.copy()
                cv2.rectangle(overlay, p1, p2, col, -1)
                cv2.addWeighted(overlay, 0.20, img, 0.80, 0, img)
            cv2.rectangle(img, p1, p2, col, 2 if is_sel else 1)
            cv2.putText(img, f"D{i+1}", (p1[0] + 2, p1[1] + 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, col, 1)

        # Retângulo em progresso
        if self.drawing and self.start_pt and self.end_pt:
            cv2.rectangle(img, self.start_pt, self.end_pt, (255, 255, 255), 1)

        # ── painel lateral ────────────────────────────────────────────────────
        canvas = np.zeros((self.disp_h, self.disp_w + 270, 3), dtype=np.uint8)
        canvas[:, :self.disp_w] = img
        panel = canvas[:, self.disp_w:]
        panel[:] = (22, 22, 22)

        col_tk = TABLE_COLORS[self.active_tk]
        dk_sel = self._active_key()
        r_sel  = self.regions[self.active_tk].get(dk_sel, [0, 0, 0, 0])

        cv2.putText(panel, f"Mesa: {self.active_tk}",
                    (5, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.38, col_tk, 1)
        cv2.putText(panel, dk_sel,
                    (5, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.38, COLOR_ACTIVE, 1)
        cv2.putText(panel, f"x={r_sel[0]} y={r_sel[1]}  {r_sel[2]}x{r_sel[3]}",
                    (5, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (130, 130, 130), 1)
        cv2.line(panel, (0, 62), (269, 62), (50, 50, 50), 1)

        for i, dk in enumerate(DEALER_KEYS):
            y_pos  = 80 + i * 22 + 14
            is_sel = (i == self.active_seat)
            col    = COLOR_ACTIVE if is_sel else COLOR_INACTIVE
            if is_sel:
                cv2.rectangle(panel, (0, y_pos - 14), (269, y_pos + 6),
                              (50, 50, 50), -1)
            r = self.regions[self.active_tk].get(dk, [0, 0, 0, 0])
            cv2.putText(panel, f"seat_{i+1}", (5, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38,
                        (255, 255, 255) if is_sel else col, 1)
            cv2.putText(panel, f"{r[0]},{r[1]}  {r[2]}x{r[3]}", (72, y_pos),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30,
                        (140, 140, 140) if is_sel else (70, 70, 70), 1)

        # Info de vídeo
        if self._is_vid:
            sec = self._fidx / self._fps
            cv2.putText(panel, f"frame {self._fidx}/{self._total}  ({sec:.0f}s)",
                        (5, self.disp_h - 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (65, 65, 65), 1)

        # Atalhos no rodapé
        foot_y = self.disp_h - 52
        cv2.line(panel, (0, foot_y - 8), (269, foot_y - 8), (45, 45, 45), 1)
        for line in [
            "S=salvar  Q=sair",
            "N/B=seat  T/1-4=mesa",
            "setas/WASD=move 1px",
            "IJKL=resize  Esp=frame",
        ]:
            cv2.putText(panel, line, (5, foot_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.30, (65, 65, 65), 1)
            foot_y += 13

        return canvas

    # ── loop principal ────────────────────────────────────────────────────────

    def run(self):
        while True:
            cv2.imshow(self._win, self._draw())
            key = cv2.waitKey(30) & 0xFF

            if   key == ord('q'):
                break
            elif key == ord('s'):
                self._save()

            # Mesa ativa
            elif key == ord('t'):
                idx = (TABLE_KEYS.index(self.active_tk) + 1) % len(TABLE_KEYS)
                self.active_tk = TABLE_KEYS[idx]
            elif key in (ord('1'), ord('2'), ord('3'), ord('4')):
                self.active_tk = TABLE_KEYS[int(chr(key)) - 1]

            # Seat ativo
            elif key == ord('n'):
                self.active_seat = (self.active_seat + 1) % N_SEATS
            elif key == ord('b'):
                self.active_seat = (self.active_seat - 1) % N_SEATS

            # Navegação de frames (vídeo)
            elif key in (ord(' '), ord('.')):
                self._advance(STEP_FRAMES)
            elif key == ord(','):
                self._advance(-STEP_FRAMES)

            # Mover região — setas (82=↑ 84=↓ 81=← 83=→ no Linux; WASD como fallback)
            elif key == 82 or key == ord('w'):
                self._move(0, -1)
            elif key == 84 or key == ord('s'):
                self._move(0, +1)
            elif key == 81 or key == ord('a'):
                self._move(-1, 0)
            elif key == 83 or key == ord('d'):
                self._move(+1, 0)

            # Redimensionar região — IJKL  (I=h↑ K=h↓ J=w← L=w→)
            elif key == ord('i'):
                self._resize(0, -1)
            elif key == ord('k'):
                self._resize(0, +1)
            elif key == ord('j'):
                self._resize(-1, 0)
            elif key == ord('l'):
                self._resize(+1, 0)

        cv2.destroyAllWindows()
        if self._is_vid:
            self._cap.release()


# ── entrada ───────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Uso: python calibrate_dealer.py <frame.png | video.mp4>")
        sys.exit(1)
    DealerCalibrator(sys.argv[1]).run()


if __name__ == "__main__":
    main()
