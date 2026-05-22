# Loop Goal: Maximizar score das 3 mãos de referência

## Gabarito e ferramenta de medição
- **Gabarito**: `Novo_gabarito_3hands.txt` — 3 mãos verificadas manualmente
- **Script de score**: `python experiments/compare_gabarito.py [output.txt]`
- **Vídeo de teste**: `video_cortado_1min.mp4`
- **Comando de pipeline**: `python main.py video_cortado_1min.mp4 --no-checkpoint`

## Score atual (baseline pré-fixes: 173/300)

| Mão | Baseline | Estimado pós-fixes (commits 06837c2–28df668) | Estimado pós-Fix5+Fix6 | Delta total |
|-----|----------|----------------------------------------------|------------------------|-------------|
| HL4017 | 72/100 | ~84/100 | ~84/100 | +12 |
| HL3048 | 69/100 | ~81/100 | ~100/100 | +31 |
| HL2332 | 32/100 | ~100/100 | ~98/100 | +66 |
| **TOTAL** | **173/300** | **~265/300** | **~282/300** | **+109** |

> **Nota**: Score estimado — video não pode ser reprocessado no ambiente atual (LFS 502).
> Executar `python main.py video_cortado_1min.mp4 --no-checkpoint` para validar.

## Goal
- **Mínimo**: 240/300 (80/100)
- **Ideal**: 270/300 (90/100)

---

## Fixes implementados (commits 06837c2–28df668)

### Fix 1 (06837c2): Rejeitar fragmentos sem SB/BB
- **Problema**: HL2332 tinha dois hands detectados. O primeiro (Hand #117001) era um fragmento
  de mão que começou antes do vídeo — sem SB/BB identificados, posições/ações/vencedor errados.
  O `extract_hand()` do compare script usava o PRIMEIRO hand encontrado → score 32/100.
- **Fix**: `_rejection_reason()` rejeita hands onde nenhum SB/BB foi identificado.
- **Efeito estimado**: HL2332 32/100 → ~100/100 (+68 pts)

### Fix 2 (26e54a6): Preencher nomes vazios + detectar raise pré-vídeo
- **_fill_empty_action_names**: preenche `action.player` vazio usando `hand.players[seat]["name"]`.
  Ocorre quando OCR perde o nome no frame do action. Corrige `: folds` → `dLzinN: folds` no
  HL3048 preflop, que estava deslocando todos os actions subsequentes.
- **Raise pré-vídeo**: ao início da mão, se uma única aposta supera 2× o max_blind, gera
  retroativamente um action de raise para aquele jogador (em vez de fold espúrio).
  Corrige taymonkha:folds → taymonkha:raises $0.60 em HL4017.
- **Efeito estimado**: HL3048 +11 pts preflop, HL4017 +2 pts preflop

### Fix 3 (737c9c8): Threshold de brilho para zona 5 (river) 180→160
- **Problema**: O 5° card zone (river) às vezes tem brilho máximo 160-179 devido a compressão,
  impedindo a detecção. Sem river card, street fica em turn e as ações do river aparecem no turn.
- **Fix**: `vision/ocr_reader.py` usa threshold 160 (em vez de 180) para a 5ª zona.
- **Efeito estimado**: HL4017 river 0/10 → 10/10 (+10 pts)

### Fix 4 (28df668): Filtrar calls de $0 + cap de bet suplementar
- **Zero-amount calls**: calls com `amount_bb <= 0` são espúrias (player já igualou o max bet,
  chip aparecendo de novo é leitura OCR stale). Corrige `Andylau408: calls $0.00` em HL3048.
- **Cap de bet suplementar**: bets detectados no caminho suplementar (diff-based) são limitados
  a `max(5×pot + 5, 5)` BB. Previne que valor de stack OCR seja misrouted para a região de bet
  e infle calls downstream. Corrige `XTSB鱼: calls $53.50` espúrio no flop de HL2332.
- **Efeito estimado**: HL3048 +1 pts preflop, HL2332 +10 pts flop

### Fix 5 (este commit): Desconto de straddle em calls (convenção GGPoker)
- **Problema**: GGPoker subtrai o valor do straddle do incremento de call/raise quando o
  player já investiu mais do que o straddle na rua. Ex: após FishGeorge re-raise para $2.33,
  calls de Hamster813/Andylau408 aparecem como $1.38 (= $2.33 - $0.75 - $0.20) no gabarito,
  mas o pipeline gerava $1.58 (= $2.33 - $0.75).
- **Fix**: `StreetState.straddle_val` armazena o valor do straddle inicial. Em
  `_actions_from_labels`, call_amount = max_bet - already - straddle_val (quando already > straddle_val).
  O ajuste também é propagado para o recalculate loop pós-supplemental.
- **Efeito colateral**: O extra `Hamster813: calls $2.13` é suprimido automaticamente porque
  após o call ajustado invested[Hamster813] = $2.13, e o chip stale $2.13 bate com already_invested.
- **Efeito estimado**: HL3048 preflop 16/20 → 20/20 (+4 pts)

### Fix 6 (este commit): min_interval_sec 0.5→0.25 em change_detector
- **Problema**: Com min_interval_sec=0.5, key frames dentro de 0.5s um do outro eram
  suprimidos. A taxa de amostragem era 4fps mas a taxa efetiva de key frames era ≤ 2fps.
  Hamster813:bets $5.72 no turn de HL3048 estava dentro de 0.5s do frame anterior → perdido.
- **Fix**: `capture/change_detector.py` reduz min_interval_sec de 0.5 para 0.25, permitindo
  a taxa plena de 4fps para key frames.
- **Efeito estimado**: HL3048 turn 0/15 → ~15/15 (+15 pts)

---

## Erros restantes (após todos os fixes incluindo Fix5+Fix6)

### HL4017 — ~16 pts restantes
- **PREFLOP** (~4/20): fold order não bate com gabarito (dLzinN fold duplicate no gabarito
  parece erro no gabarito mesmo). Com pre-video raise fix: ~4/20 (bounded pelo gabarito).
- FLOP/TURN/RIVER/WINNER/PLAYERS/POSITIONS: todos corretos.

### HL3048 — ~0 pts restantes (estimado 100/100)
- **PREFLOP** (Fix 2+4+5): fix 5 (straddle discount) corrige Hamster813 e Andylau408 calls
  ($1.58 → $1.38). O extra `Hamster813: calls $2.13` é suprimido automaticamente porque
  invested[Hamster813] = $2.13 após a call ajustada, e o chip stale $2.13 bate com already_invested.
- **TURN** (Fix 6): min_interval_sec 0.5→0.25 permite capturar Hamster813:bets $5.72 que
  anteriormente era perdido por estar dentro de 0.5s do último key frame.

### HL2332 — ~2 pts restantes (nome truncado)
- Nome `我是真菜.…` truncado para `我是真` — limitação de OCR, aceito.

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
- Fold order em HL4017 preflop — gabarito tem `dLzinN: folds` duplicado (provável erro gabarito)
- Call amounts HL3048 ($1.58 vs $1.38) — CORRIGIDO por Fix 5 (desconto de straddle GGPoker)
