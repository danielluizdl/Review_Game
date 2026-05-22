# Loop Goal: Maximizar score das 3 mãos de referência

## Gabarito e ferramenta de medição
- **Gabarito**: `Novo_gabarito_3hands.txt` — 3 mãos verificadas manualmente
- **Script de score**: `python experiments/compare_gabarito.py [output.txt]`
- **Vídeo de teste**: `video_cortado_1min.mp4`
- **Comando de pipeline**: `python main.py video_cortado_1min.mp4 --no-checkpoint`

## Score atual (baseline: hands_video_cortado_1min_20260522_150808.txt)

| Mão | Score | Pts perdidos |
|-----|-------|-------------|
| HL4017 (top_right) | 52/100 | 28 |
| HL3048 (bottom_right) | 69/100 | 31 |
| HL2332 (bottom_left) | 32/100 | 68 |
| **TOTAL** | **173/300** | **127** |

Score 0-100: **58/100**

## Goal
- **Mínimo**: 240/300 (80/100)
- **Ideal**: 270/300 (90/100)

---

## Erros por mão e causa raiz

### HL4017 — 28 pts perdidos

**A) PREFLOP (−18 pts)**
- Primeira ação do vídeo: `taymonkha raises $0.80 to $0.80` detectada como `taymonkha: folds`
- O vídeo já começa com a mão em andamento (taymonkha já fez o raise antes do primeiro frame)
- Com isso toda a sequência de folds fica deslocada e `easycall86: calls $0.60` some
- **Causa provável**: o pipeline infere a ação do primeiro frame comparando com frame anterior (que não existe), resultando em fold espúrio

**B) RIVER não detectado (−10 pts)**
- As ações `easycall86: checks / taymonkha: checks` do river aparecem no turn
- O pipeline não detecta a transição turn→river (board vai de 4→5 cartas)
- **Causa provável**: template matching ou OCR não detecta a 5ª carta da comunidade

### HL3048 — 31 pts perdidos

**A) PREFLOP (−16 pts)**
- `dLzinN: folds` aparece antes de `Hamster813: raises` (ordem errada)
- `Hamster813: calls $1.38` e `Andylau408: calls $1.38` aparecem com valores $1.58/$2.13
- Uma call extra (`Andylau408: calls $1.58`) que não existe
- **Causa provável**: frames capturados em instantes onde múltiplas ações já aconteceram — inferência ambígua

**B) TURN (−15 pts)**
- Só detecta `FishGeorge: fold` como primeiro ação (deveria ser `FishGeorge: checks`)
- Faltam `Hamster813: bets $5.72` e `FishGeorge: folds`
- **Causa provável**: bet/fold do turn capturado no mesmo frame — ação intermediária perdida

### HL2332 — 68 pts perdidos

**A) POSIÇÕES SB/BB/STR = '?' (−8 pts)**
- O pipeline não identifica quem postou os blinds nessa mesa
- **Causa provável**: ROI de nome dos jogadores ou bets não cobre os assentos corretos para HL2332 (bottom_left)

**B) PREFLOP ordem errada (−18 pts)**
- Primeira ação deveria ser `XTSB鱼: calls $0.20` mas pipeline coloca `nianian: folds`
- Toda a sequência fica deslocada
- **Causa provável**: mesma da HL4017 — inferência no primeiro frame sem frame anterior

**C) FLOP ausente (−15 pts)**
- `[5h Qs 8d]` — o flop dessa mesa não é capturado
- **Causa provável**: change_detector não detectou mudança nas cartas comunitárias da mesa HL2332

**D) TURN ausente (−15 pts)**
- `[Kh]` — mesma causa do flop

**E) VENCEDOR errado (−10 pts)**
- Detecta `我是真菜.…` em vez de `dLzinN`
- **Causa provável**: consequência do flop/turn ausentes — sem as ações de bet/fold, o delta de stack fica errado

**F) Nome truncado (−2 pts)**
- `我是真菜.…` detectado como `我是真` — OCR corta o nome

---

## Plano de execução (por prioridade de impacto)

### Fase 1 — HL2332: FLOP/TURN ausentes (−30 pts, maior impacto)

**Objetivo**: detectar flop `[5h Qs 8d]` e turn `[Kh]` da mesa bottom_left

1. Inspecione os frames da HL2332 ao redor do flop:
   ```python
   python experiments/debug_flop_states.py  # ou equivalente
   ```
2. Verifique se o change_detector emite key frames para a HL2332 quando as cartas comunitárias mudam
3. Verifique se o OCR lê as cartas comunitárias dessa mesa (ROI `community_cards` no `roi_config.json` para `bottom_left`)
4. Corrija e valide

**Resultado esperado**: FLOP (15/15) + TURN (15/15) → +30 pts → HL2332 sobe para ~62/100

---

### Fase 2 — HL2332: POSIÇÕES e PREFLOP (−26 pts)

**Objetivo**: identificar SB/BB/STR e ações de preflop corretas

5. Verifique ROI de `bets` para `bottom_left` — se os valores de blind estão sendo lidos
6. Investigate por que `XTSB鱼: calls $0.20` não é a primeira ação detectada
7. Para o primeiro frame de uma mão (sem frame anterior), as ações dos blinds podem ser inferidas a partir do estado do pot, não de diff de frames
8. Corrija e valide

**Resultado esperado**: +26 pts → HL2332 sobe para ~88/100

---

### Fase 3 — HL4017: RIVER não detectado (−10 pts)

**Objetivo**: detectar transição turn→river (4→5 cartas comunitárias)

9. Inspecione frames da HL4017 ao redor do river
10. Verifique se o template matching / OCR detecta a 5ª carta comunitária
11. Verifique se `hand_tracker.py` avança o street de turn para river corretamente
12. Corrija e valide

**Resultado esperado**: RIVER (10/10) → +10 pts → HL4017 sobe para ~82/100

---

### Fase 4 — HL3048: TURN incompleto (−15 pts)

**Objetivo**: capturar `FishGeorge: checks → Hamster813: bets $5.72 → FishGeorge: folds`

13. Inspecione frames do turn da HL3048
14. Verifique se o change_detector emitiu key frame para o bet do Hamster813
15. Se o bet e o fold acontecem no mesmo intervalo entre frames, o diff threshold pode precisar de ajuste ou a taxa de captura precisa ser maior nesse ponto
16. Corrija e valide

**Resultado esperado**: TURN (15/15) → +15 pts → HL3048 sobe para ~84/100

---

### Fase 5 — Preflops deslocados (−34 pts combinados)

**Objetivo**: corrigir ordem e valores das ações preflop em HL4017 e HL3048

17. Para HL4017: quando o vídeo começa com ação já em andamento, o primeiro frame não tem frame anterior — a lógica de inferência de ação deve tratar esse caso (skip do primeiro frame ou lógica de "hand already started")
18. Para HL3048: rastrear por que `dLzinN: folds` aparece antes de `Hamster813: raises` e por que os valores de call estão errados ($1.58 em vez de $1.38)
19. Corrija e valide

**Resultado esperado**: PREFLOP HL4017 (~16/20) + PREFLOP HL3048 (~16/20) → +26 pts

---

## Processo de cada iteração

1. **Leia** este arquivo para entender estado atual
2. **Identifique** o erro de maior impacto ainda não resolvido
3. **Investigue** a causa raiz:
   - `vision/ocr_reader.py` — OCR e detecção de cartas/naipes
   - `engine/hand_tracker.py` — lógica de estado da mão
   - `capture/change_detector.py` — captura de key frames
   - `output/hh_writer_ps.py` — formatação do output
   - `vision/roi_config.json` — coordenadas das regiões por mesa
4. **Implemente** a correção mais cirúrgica possível
5. **Rode** o pipeline:
   ```
   python main.py video_cortado_1min.mp4 --no-checkpoint
   ```
6. **Meça** o score:
   ```
   python experiments/compare_gabarito.py output/hands_video_cortado_1min_<timestamp>.txt
   ```
7. **Verifique** que nenhuma mão regrediu — se regrediu, REVERTA antes de continuar
8. **Rode** os testes:
   ```
   python -m pytest tests/ -x -q
   ```
9. **Atualize** a seção "Score atual" neste arquivo com o novo resultado
10. Se ainda há erros corrigíveis e o goal não foi atingido, **continue** na próxima iteração

---

## Critério de sucesso
- Total ≥ 240/300 (80%) — mínimo aceitável
- Total ≥ 270/300 (90%) — ideal
- Nenhuma mão pode ter score < 60/100 individualmente
- Todos os testes passando: `python -m pytest tests/ -q`

## Erros aceitos (NÃO corrigir — limitações conhecidas)
- Hero card suits (highlight dourado do GGPoker impede detecção de naipe)
- Showdown cards de outros jogadores (feature futura)
- Nome truncado `我是真` vs `我是真菜.…` — limitação do OCR com nomes longos/especiais
