# Loop Goal: Aproximar output do gabarito (3 mãos)

## Gabarito de referência
`Novo_gabarito_3hands.txt` — 3 mãos completas e verificadas manualmente.

## Mãos-alvo
- **HL4017** (top_right) — primeira mão completa de HL4017
- **HL3048** (bottom_right) — primeira mão completa de HL3048
- **HL2332** (bottom_left) — mão #2287002 de HL2332

## Referência de formato
`HH_FORMAT_REFERENCE.md` — guia completo de todas as situações possíveis numa mão.

---

## Erros conhecidos a corrigir (por prioridade)

### HL4017 — 4 erros críticos

1. **Flop AUSENTE** — output mostra `*** TURN *** [] [As]` sem flop detectado.
   - Gabarito: `*** FLOP *** [Jd 5s 2h]`
   - Mesa: top_right. Investigar por que o flop desta mesa não é capturado.

2. **Turn card errado** — output `[As]`, gabarito `[3d]`

3. **River card errado** — output `[3h]`, gabarito `[7s]`
   - (turn/river podem estar trocados por causa do flop ausente)

4. **Showdown ausente** — output `taymonkha: doesn't show hand`
   - Gabarito:
     ```
     *** SHOW DOWN ***
     taymonkha: shows [Ac Td] (high card Ace - Ten kicker)
     easycall86: shows [Ah 8c] (high card Ace)
     taymonkha collected $2.15 from pot
     ```
   - Summary seats sem `showed [X] and won/lost`

### HL3048 — 0 erros ✅ (NÃO regredir)

**Gabarito corrigido (2026-05-21)**:
- `FishGeorge ($49.70 in chips)` — era `$50.20` no gabarito antigo
- `Dealt to dLzinN [2h 6d]` — era `[2c 65]` no gabarito antigo (OCR garbled)

### HL2332 (#2287002) — 12 erros

5. **Hero cards** — output `[4h]` (1 carta), gabarito `[Ah Ad]`

6. **Stacks errados** (5 jogadores com diferença de $0.10–$0.30):
   - 啦啦啦的啦: output `$10.50` vs gabarito `$10.40`
   - 都看到可能: output `$37.40` vs gabarito `$37.20`
   - ElBandido: output `$85.30` vs gabarito `$85.00`
   - XTSB鱼: output `$60.50` vs gabarito `$60.40`
   - 我是真菜.…: output `$35.60` vs gabarito `$35.20`

7. **Flop errado** — output `[5h 8h Ad]`, gabarito `[5h Qs 8d]`
   - Só a 1ª carta bate (5h); 2ª e 3ª erradas

8. **Turn naipe errado** — output `Kd`, gabarito `Kh`

9. **Ações faltando no pré-flop** — XTSB鱼 calls $0.20 ausente

10. **Ações faltando no flop** — `dLzinN: bets $0.92` e `XTSB鱼: calls $0.92` ausentes

11. **Ação faltando no turn** — `dLzinN: bets $2.36` ausente

12. **Uncalled bet ausente** — `Uncalled bet ($2.36) returned to dLzinN` ausente

13. **Valor coletado errado** — output `$7.07`, gabarito `$4.71`
    - (consequência direta do uncalled bet ausente)
    - **Gabarito corrigido (2026-05-21)**: `Total pot $4.71` (não `$7.07`) — pot = líquido após devolver uncalled bet

14. **Board errado no summary** — output `[5h 8h Ad Kd]`, gabarito `[5h Qs 8d Kh]`

### Erros aceitos (NÃO corrigir — limitações conhecidas)
- Hero card suits (highlight dourado do GGPoker impede detecção de naipe)
- Showdown cards de outros jogadores (feature futura)

---

## Processo de cada iteração

1. Leia este arquivo (LOOP_GOAL.md) para entender o estado atual
2. Identifique o erro mais impactante que ainda não foi resolvido
3. Investigue a causa raiz lendo os arquivos relevantes:
   - `vision/ocr_reader.py` — OCR e detecção de cartas/naipes
   - `engine/hand_tracker.py` — lógica de estado da mão
   - `capture/change_detector.py` — captura de key frames
   - `output/hh_writer_ps.py` — formatação do output
4. Implemente a correção mais cirúrgica possível
5. Rode: `python main.py video_teste_reduzido.mp4 --no-checkpoint`
6. Leia o output mais recente: `output/hands_video_teste_reduzido_*.txt`
7. Extraia as 3 mãos-alvo e compare campo a campo com `Novo_gabarito_3hands.txt`
8. **CRÍTICO**: verifique que HL3048 ainda está 100% correto — se regrediu, REVERTA
9. Rode os testes: `python -m pytest tests/ -x -q`
10. Atualize a seção "Contagem atual de erros" abaixo
11. Se ainda há erros corrigíveis, continue na próxima iteração

---

## Contagem atual de erros (baseline — output 20260521_192230)

| Mão | Erros críticos | Erros de dados |
|-----|----------------|----------------|
| HL4017 | 4 (flop ausente, turn errado, river errado, showdown ausente) | 0 |
| HL3048 | 0 ✅ | 0 |
| HL2332 | 4 (hero cards, flop, turn naipe, showdown) | 8 (5 stacks, 3 ações faltando, uncalled bet, pot) |
| **Total** | **8** | **8** |

**Total geral: 16 erros** (excluindo hero card suits e showdown de terceiros)

---

## Critério de sucesso
- HL3048: manter 100% ✅
- HL4017: flop `[Jd 5s 2h]` + turn `[3d]` + river `[7s]` detectados
- HL2332: flop `[5h Qs 8d]` + turn `Kh` + ações preflop/flop/turn capturadas
- Total de erros < 5
