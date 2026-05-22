"""
Extrai imagens de 52 cartas de um frame de vídeo.

Uso:
  python extract_card_templates.py <frame.png> [output_dir]

  Exemplo:
  python extract_card_templates.py key_frames/frame_0.png vision/card_templates

Este script é um placeholder. A extração real envolve:
1. Abrir um frame que tem um flop visível (3 cartas comunitárias)
2. Manualmente identificar bounding box de cada carta
3. Copiar para pasta vision/card_templates/ com nome RANK+SUIT.png
"""
import cv2
import os
import numpy as np
from pathlib import Path
import sys


def create_placeholder_templates(output_dir: str = "vision/card_templates"):
    """
    Cria templates placeholder para teste.
    Na produção, substituir por extração real de um frame com cartas.
    """
    os.makedirs(output_dir, exist_ok=True)

    ranks = "A23456789TJQK"
    suits = {"d": "Diamonds", "h": "Hearts", "c": "Clubs", "s": "Spades"}

    for suit_code, suit_name in suits.items():
        for rank in ranks:
            card_name = f"{rank}{suit_code}"
            # Criar imagem placeholder (100x140 pixels, cor de fundo único)
            if suit_code == "d":
                color = (0, 165, 255)  # Laranja (diamonds em GGPoker)
            elif suit_code == "h":
                color = (0, 0, 255)  # Vermelho (hearts)
            elif suit_code == "c":
                color = (0, 128, 0)  # Verde (clubs)
            else:  # spades
                color = (0, 0, 0)    # Preto (spades)

            img = np.full((140, 100, 3), color, dtype=np.uint8)

            # Adicionar text com rank + suit para debug visual
            text = rank + suit_code
            cv2.putText(
                img, text,
                (30, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                2, (255, 255, 255),
                3
            )

            # Salvar
            path = os.path.join(output_dir, f"{card_name}.png")
            cv2.imwrite(path, img)
            print(f"  Criado: {path}")

    print(f"\n✓ {len(ranks) * len(suits)} templates placeholder criados em {output_dir}/")
    print("\n⚠️  IMPORTANTE: Estes são placeholders!")
    print("Para templates REAIS, siga este processo manual:\n")
    print("1. Abra um frame GGPoker com flop visível:")
    print("   python -c \"import cv2; frame = cv2.imread('key_frames/frame_X.png'); cv2.imshow('', frame); cv2.waitKey(0)\"")
    print("\n2. Identifique ROI de cada carta (x, y, w, h)")
    print("\n3. Extraia com:")
    print("   card_img = frame[y:y+h, x:x+w]")
    print("   cv2.imwrite('vision/card_templates/Ad.png', card_img)")
    print("\n4. Repita para todas as 52 cartas")


def extract_from_frame(frame_path: str, output_dir: str = "vision/card_templates"):
    """
    Tenta extrair cartas de um frame automaticamente.
    Funcionará melhor se o frame tiver cartas bem definidas e isoladas.
    """
    if not os.path.exists(frame_path):
        print(f"❌ Frame não encontrado: {frame_path}")
        return

    img = cv2.imread(frame_path)
    if img is None:
        print(f"❌ Erro ao carregar: {frame_path}")
        return

    print(f"✓ Frame carregado: {img.shape}")

    # Para GGPoker em 1920x1080, cartas têm ~80-120px de largura
    # Detectar regiões brancas (fundo de cartas)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    os.makedirs(output_dir, exist_ok=True)

    extracted = 0
    for i, contour in enumerate(contours):
        x, y, w, h = cv2.boundingRect(contour)
        # Filtrar por tamanho (cartas típicas)
        if 50 < w < 150 and 70 < h < 200:
            card_roi = img[y:y+h, x:x+w]
            # Salvar com nome genérico (não posso inferir rank/suit automaticamente)
            out_path = os.path.join(output_dir, f"card_{i:02d}.png")
            cv2.imwrite(out_path, card_roi)
            extracted += 1
            print(f"  Extraído [{i}]: {out_path} ({w}x{h}px)")

    print(f"\n⚠️  {extracted} regiões extraídas, mas não foram nomeadas (Ad, Kd, etc.)")
    print("Próximo passo: renomear manualmente ou usar OCR para confirmar rank+suit\n")


def main():
    if len(sys.argv) > 1:
        frame_path = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else "vision/card_templates"

        print(f"Tentando extrair de frame: {frame_path}")
        extract_from_frame(frame_path, output_dir)
    else:
        print("Modo: criar templates placeholder para teste")
        create_placeholder_templates()


if __name__ == "__main__":
    main()
