# Loop Goal: Maximizar score das 3 mãos de referência

## Gabarito e ferramenta de medição
- **Gabarito**: `Novo_gabarito_3hands.txt` — 3 mãos verificadas manualmente
- **Script de score**: `python experiments/compare_gabarito.py [output.txt]`
- **Vídeo de teste**: `video_cortado_1min.mp4`
- **Comando de pipeline**: `python main.py video_cortado_1min.mp4 --no-checkpoint`

## Score atual (pós fixes de agentes: ~265/300 estimado, não validado)

| Mão | Baseline | Pós-agentes (estimado) | Máximo atingível | Limitação |
|-----|----------|------------------------|-----------------|-----------|
| HL4017 | 72/100 | ~84/100 | **84/100** | Gabarito com erro (ver abaixo) |
| HL3048 | 69/100 | ~81/100 | **96/100** | Calls $0.20 off (aceito) |
| HL2332 | 32/100 | ~100/100 | **100/100** | — |
| **TOTAL** | **173/300** | **~265/300** | **~280/300** | |

> **Nota**: Score pós-agentes é estimado. Validar com `python main.py video_cortado_1min.mp4 --no-checkpoint`

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

## Próxima iteração: 2 fixes para HL3048 turn (+15 pts → total ~280/300)

### Fix A — Converter stack-delta "unknown" em bet/raise correto
**Problema**: `_infer_actions()` detecta a queda de stack do Hamster813 (de ~$32.90 para ~$27.18
= drop de $5.72) mas emite `action_type = "unknown"`. O compare_gabarito não dá crédito para
ações "unknown". O bet real de $5.72 aconteceu entre dois frames e sumiu antes do próximo sample.

**Arquivo**: `engine/hand_tracker.py`

**Localização**: `_infer_actions()`, bloco `elif (prev_bet < 0.05 and curr_bet < 0.05 ...)` — linhas ~361-367.

**Fix cirúrgico**: Substituir `"unknown"` pela classificação correta com base em `state.max_bet`:

```python
elif (prev_bet < 0.05 and curr_bet < 0.05
      and prev_stack is not None and curr_stack is not None):
    stack_drop = round(prev_stack - curr_stack, 2)
    if stack_drop > 0.5:
        prev_max = state.max_bet
        if prev_max < 0.05:
            action_type = "bet"
            amount_bb   = stack_drop
            state.max_bet          = stack_drop
            state.voluntary_raises += 1
            state.last_aggressor   = sk
        else:
            action_type = "raise"
            amount_bb   = round(stack_drop - prev_max, 2)
            state.max_bet          = max(state.max_bet, stack_drop)
            state.voluntary_raises += 1
            state.last_aggressor   = sk
        state.invested[sk] = round(state.invested.get(sk, 0.0) + stack_drop, 2)
        state.has_acted.add(sk)
        action = Action(sk, name, pos, action_type, amount_bb, street, ts,
                        total_bb=state.invested[sk])
        actions.append(action)
```

**Efeito esperado**: `Hamster813: bets $5.72` aparece no turn → gabarito turn[2] ✓

---

### Fix B — Não emitir fold no frame imediatamente após transição de rua
**Problema**: No primeiro frame do turn após a transição, as fichas residuais do flop de
FishGeorge ainda estão sendo varridas para o pot (animação de coleta). O `_infer_actions`
vê a ficha desaparecer e emite `FishGeorge: fold` falso (turn[1]).

O código já pula inferência **no frame de transição** (`is_new_street=True → new_actions=[]`)
mas a animação de sweep ocorre no frame SEGUINTE.

**Arquivo**: `engine/hand_tracker.py`

**Fix**: Adicionar campo `just_transitioned: bool = False` ao `StreetState`. Setar para `True`
quando nova rua for detectada. No frame seguinte, pular detecção de fold (mas não de bet/raise).
Limpar após usar.

**Mudança 1** — Dataclass `StreetState` (adicionar campo):
```python
just_transitioned: bool = False
```

**Mudança 2** — Em `process_sequence()`, após resetar o StreetState para nova rua (bloco
`if effective_n > prev_max:`):
```python
new_ss.just_transitioned = True
```

**Mudança 3** — Em `_infer_actions()`, no bloco `elif prev_bet > 0.05 and curr_bet < 0.05:`
(detecção de call/fold por desaparecimento de chip), adicionar no início do bloco:
```python
if state.just_transitioned:
    state.just_transitioned = False
    continue   # Chip desapareceu por sweep de transição, não por ação
```

**Importante**: Limpar o flag fora do `continue` também (no `else` path) para garantir que
seja limpo mesmo para assentos sem chip naquele frame. Melhor limpar antes do loop de assentos:

```python
# No início da função _infer_actions, antes do loop de assentos:
just_trans = state.just_transitioned
state.just_transitioned = False  # Limpa sempre — vale só 1 frame
```

E no bloco de fold:
```python
elif prev_bet > 0.05 and curr_bet < 0.05:
    if just_trans:
        continue  # sweep de transição, não ação
    # ... resto do código existente
```

**Efeito esperado**: `FishGeorge: checks` não vira fold falso → turn[1] ✓

---

### Fix C — Terminal fold (automático com A+B)
`_infer_terminal_folds` já está implementado. Com Fix A (Hamster813 bet detectado) e Fix B
(FishGeorge check preservado), a função vai encontrar:
- FishGeorge última ação no turn = check
- Agressão posterior = Hamster813: bets $5.72
- → Insere `FishGeorge: folds` automaticamente ✓

**Nenhuma mudança de código necessária para Fix C.**

---

## Processo de cada iteração

1. **Leia** este arquivo para entender estado atual
2. **Valide** o score atual rodando o pipeline + compare:
   ```
   python main.py video_cortado_1min.mp4 --no-checkpoint
   python experiments/compare_gabarito.py output/hands_video_cortado_1min_<timestamp>.txt
   ```
3. **Implemente** Fix A (stack-delta bet/raise) em `engine/hand_tracker.py`
4. **Implemente** Fix B (just_transitioned flag) em `engine/hand_tracker.py`
5. **Rode** o pipeline e meça score — verificar que HL3048 turn subiu e nada regrediu
6. **Rode** os testes: `python -m pytest tests/ -x -q`
7. **Atualize** a seção "Score atual" deste arquivo com resultado real
8. Se score < 280/300 e há bugs restantes, continue investigando

---

## Erros aceitos (NÃO corrigir — limitações conhecidas)

- **HL4017 preflop fold order**: gabarito tem `dLzinN: folds` duplicado — erro no gabarito
- **HL3048 calls $0.20 off** ($1.58 vs $1.38): diferença de contabilidade de antes
- **Hero card suits**: highlight dourado do GGPoker impede detecção de naipe
- **Nome truncado** `我是真` vs `我是真菜.…`: limitação do OCR com nomes longos

---

## Critério de sucesso desta iteração
- Total ≥ 275/300
- HL3048 turn ≥ 10/15
- Nenhuma mão regrediu abaixo do score pós-agentes
- Todos os testes passando: `python -m pytest tests/ -q`
