# Loop Goal: Maximizar score das 3 mãos de referência

## Gabarito e ferramenta de medição
- **Gabarito**: `Novo_gabarito_3hands.txt` — 3 mãos verificadas manualmente
- **Script de score**: `python experiments/compare_gabarito.py [output.txt]`
- **Vídeo de teste**: `video_cortado_1min.mp4`
- **Comando de pipeline**: `python main.py video_cortado_1min.mp4 --no-checkpoint`

## Score atual (estimado, validar com pipeline)

| Mão | Baseline | Pós-commits 06837c2–28df668 | Pós-Fix5+Fix6 (commit 0ea7786) | Máximo atingível |
|-----|----------|-----------------------------|-------------------------------|-----------------|
| HL4017 | 72/100 | ~84/100 | ~84/100 | **84/100** (gabarito com erro) |
| HL3048 | 69/100 | ~81/100 | ~100/100 | **100/100** |
| HL2332 | 32/100 | ~100/100 | ~98/100 | **98/100** (nome truncado) |
| **TOTAL** | **173/300** | **~265/300** | **~282/300** | **~282/300** |

> **Nota**: Score estimado — video não pode ser reprocessado no ambiente atual (LFS 502).
> Executar `python main.py video_cortado_1min.mp4 --no-checkpoint` para validar.

---

## Teto do HL4017 preflop — erro confirmado no gabarito

O gabarito (`Novo_gabarito_3hands.txt`) tem `dLzinN: folds` duplicado (linhas 26 e 29) e a
ordem dos folds não corresponde às posições reais de cada assento. A sequência correta baseada
nas posições (UTG→BTN→SB→BB→STR) seria:

```
GongFuBoy → Fahir651 → 老胡头 → dLzinN → Phoenixy → 浅忆心安 → easycall86 calls
```

O gabarito tem uma ordem errada e dLzinN duplicado. **Impossível chegar a 20/20 no preflop
do HL4017 sem reproduzir o erro do gabarito.** Não corrigir.

---

## Fixes implementados (commits 06837c2–0ea7786)

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

### Fix 5 (0ea7786): Desconto de straddle em calls (convenção GGPoker)
- **Problema**: GGPoker subtrai o valor do straddle do incremento de call/raise quando o
  player já investiu mais do que o straddle na rua. Ex: após FishGeorge re-raise para $2.33,
  calls de Hamster813/Andylau408 aparecem como $1.38 (= $2.33 - $0.75 - $0.20) no gabarito,
  mas o pipeline gerava $1.58 (= $2.33 - $0.75).
- **Fix**: `StreetState.straddle_val` armazena o valor do straddle inicial. Em
  `_actions_from_labels`, call_amount = max_bet - already - straddle_val (quando already > straddle_val).
  O ajuste também é propagado para o recalculate loop pós-supplemental e para `ss_tmp`.
- **Efeito colateral**: O extra `Hamster813: calls $2.13` é suprimido automaticamente porque
  após o call ajustado invested[Hamster813] = $2.13, e o chip stale $2.13 bate com already_invested.
- **Efeito estimado**: HL3048 preflop 16/20 → 20/20 (+4 pts)

### Fix 6 (0ea7786): min_interval_sec 0.5→0.25 em change_detector
- **Problema**: Com min_interval_sec=0.5, key frames dentro de 0.5s um do outro eram
  suprimidos. A taxa de amostragem era 4fps mas a taxa efetiva de key frames era ≤ 2fps.
  Hamster813:bets $5.72 no turn de HL3048 estava dentro de 0.5s do frame anterior → perdido.
- **Fix**: `capture/change_detector.py` reduz min_interval_sec de 0.5 para 0.25, permitindo
  a taxa plena de 4fps para key frames.
- **Efeito estimado**: HL3048 turn 0/15 → ~15/15 (+15 pts)

---

## Erros restantes após Fix5+Fix6

### HL4017 — ~16 pts restantes (irreversíveis — gabarito com erro)
- **PREFLOP** (~4/20): fold order não bate com gabarito (dLzinN fold duplicate — erro gabarito).
- FLOP/TURN/RIVER/WINNER/PLAYERS/POSITIONS: todos corretos.

### HL3048 — ~0 pts restantes (estimado 100/100 pós Fix5+Fix6)
- PREFLOP: Fix 2+4+5 resolvem todos os erros.
- TURN: Fix 6 deve capturar Hamster813:bets $5.72 e FishGeorge:folds.

### HL2332 — ~2 pts restantes (nome truncado — aceito)
- Nome `我是真菜.…` truncado para `我是真` — limitação do OCR, aceito.

---

## Backup: Fix A+B para turn HL3048 (se Fix6 não resolver)

Se Fix6 (min_interval_sec) não for suficiente para capturar o turn bet, implementar:

### Fix A — Converter stack-delta "unknown" em bet/raise correto
**Problema**: `_infer_actions()` detecta a queda de stack do Hamster813 (de ~$32.90 para ~$27.18
= drop de $5.72) mas emite `action_type = "unknown"`. O compare_gabarito não dá crédito para
ações "unknown". O bet real de $5.72 aconteceu entre dois frames e sumiu antes do próximo sample.

**Arquivo**: `engine/hand_tracker.py`, bloco `elif (prev_bet < 0.05 and curr_bet < 0.05 ...)`:
```python
stack_drop = round(prev_stack - curr_stack, 2)
if stack_drop > 0.5:
    prev_max = state.max_bet
    action_type = "bet" if prev_max < 0.05 else "raise"
    amount_bb   = stack_drop if prev_max < 0.05 else round(stack_drop - prev_max, 2)
    state.max_bet = max(state.max_bet, stack_drop)
    state.voluntary_raises += 1
    state.last_aggressor = sk
    state.invested[sk] = round(state.invested.get(sk, 0.0) + stack_drop, 2)
    state.has_acted.add(sk)
    actions.append(Action(sk, name, pos, action_type, amount_bb, street, ts,
                          total_bb=state.invested[sk]))
```

**Efeito esperado**: `Hamster813: bets $5.72` aparece no turn → gabarito turn[2] ✓

### Fix B — Não emitir fold no frame imediatamente após transição de rua
**Problema**: No primeiro frame pós-transição, fichas do flop ainda estão sendo varridas
para o pot. `_infer_actions` vê chip desaparecer → fold falso (FishGeorge: fold no turn[1]).

**Fix**: Adicionar `just_transitioned: bool = False` ao `StreetState`. Setar `True` ao resetar
o estado para nova rua. Em `_infer_actions`, pular detecção de fold quando `just_transitioned`.

### Fix C — Terminal fold (automático com A+B)
`_infer_terminal_folds` já está implementado. Com Fix A (bet detectado) e Fix B (check preservado):
- FishGeorge última ação no turn = check
- Agressão posterior = Hamster813: bets $5.72
- → Insere `FishGeorge: folds` automaticamente ✓ (nenhuma mudança de código necessária)

---

## Processo de cada iteração

1. **Leia** este arquivo para entender estado atual
2. **Rode** o pipeline: `python main.py video_cortado_1min.mp4 --no-checkpoint`
3. **Meça** o score: `python experiments/compare_gabarito.py output/hands_video_cortado_1min_<timestamp>.txt`
4. **Verifique** que nenhuma mão regrediu
5. **Rode** os testes: `python -m pytest tests/ -x -q`
6. **Atualize** a seção "Score atual" neste arquivo com o novo resultado

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
- Fold order em HL4017 preflop — gabarito tem `dLzinN: folds` duplicado (erro no gabarito)
