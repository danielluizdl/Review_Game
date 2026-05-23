# Loop Goal: Maximizar score das 3 mãos de referência

## Gabarito e ferramenta de medição
- **Gabarito**: `Novo_gabarito_3hands.txt` — 3 mãos verificadas manualmente
- **Script de score**: `python experiments/compare_gabarito.py [output.txt]`
- **Vídeo de teste**: `video_cortado_1min.mp4`
- **Comando de pipeline**: `python main.py video_cortado_1min.mp4 --no-checkpoint`

---

## Histórico de scores validados (mundo real)

| Run | Output | HL4017 | HL3048 | HL2332 | TOTAL | Commits ativos |
|-----|--------|--------|--------|--------|-------|----------------|
| Baseline | hands_*_150808.txt | 72 | 69 | 32 | **173** | pré-fixes |
| Pós fixes 1-4 | hands_*_205149.txt | 74 | 80 | 90 | **244** | 06837c2–28df668 |
| Pós fixes 1-6 | hands_*_212123.txt | 84 | 57 | 80 | **221** | 06837c2–0ea7786 |

**Fix 5+6 causou regressão líquida de -23 pts** (244 → 221).

---

## Análise da regressão — Fix 5 e Fix 6

### Fix 3 funcionou (HL4017 river: 0/10 → 10/10 = +10 pts) ✅
O threshold 160 para a zona 5 do river está correto. HL4017 chegou ao seu **teto definitivo de 84/100**
(os 16 pts restantes são erro confirmado no gabarito — `dLzinN: folds` duplicado, não corrigir).

### Fix 6 causou regressão grave no HL3048 (-23 pts) ❌
**O que mudou**: `min_interval_sec` de 0.5 → 0.25 em `capture/change_detector.py`.
**Efeito**: frames capturados subiram de **101 → 140** (+39%).

**Problema concreto no HL3048**:
Com mais frames no preflop, o tracker capturou estados intermediários da animação de apostas
(chips ainda em transição). Isso gerou ações espúrias que se misturaram com as reais:

```
# O que aparece agora no preflop (errado):
extra [12]: Hamster813: calls $2.13   ← ação espúria
extra [13]: Andylau408: calls $1.18   ← ação espúria
extra [14]: Andylau408: checks        ← ação espúria (flop vazou pro preflop)
extra [15]: FishGeorge: checks        ← ação espúria (flop vazou pro preflop)
extra [16]: Hamster813: bets $2.27    ← ação espúria (flop vazou pro preflop)
extra [17]: Andylau408: folds         ← ação espúria (flop vazou pro preflop)
extra [18]: FishGeorge: calls $2.27   ← ação espúria (flop vazou pro preflop)
extra [19]: FishGeorge: checks        ← ação espúria (turn vazou pro preflop)
```

Com as ações do flop e turn aparecendo no preflop, o score real do flop e turn zerou:
- Preflop: 15/20 → 7/20 (-8)
- Flop: 15/15 → 0/15 (-15)
- Turn: 0/15 → 0/15 (igual, mas por razão diferente)

**Causa raiz do Fix 6**: A hipótese de que frames mais frequentes capturariam
`Hamster813: bets $5.72` no turn estava errada. O bet desapareceu dentro de 0.25s
(uma única animação de ~6 frames a 30fps), então nem 0.25s de intervalo é suficiente.
O que o Fix 6 fez foi apenas capturar mais frames de transição/animação, introduzindo ruído.

### Fix 5 pode ter causado regressão no HL3048 preflop ⚠️
**O que mudou**: desconto de straddle em calls — `call_amount = max_bet - already - straddle_val`.

Antes do Fix 5 (run 205149): preflop HL3048 = **15/20**
Depois do Fix 5+6 (run 212123): preflop HL3048 = **7/20** (mas Fix 6 contamina a análise)

Não é possível isolar o impacto do Fix 5 sem reverter o Fix 6. É necessário reverter Fix 6
primeiro e medir o Fix 5 isolado para saber se ele ajuda ou atrapalha.

### Fix 5 causou regressão no HL2332 turn (-10 pts) ❌
Antes (run 205149): HL2332 turn = **15/15** ✓
Depois (run 212123): HL2332 turn = **5/15** — faltando `XTSB鱼: folds` no turn[3]

```
TURN (5/15):
  [2] player: 'dLzinN' vs 'XTSB鱼'; tipo: 'bet' vs 'fold'; valor: $2.36 vs $0.0
  faltando [3]: XTSB鱼: folds
```

O `dLzinN: bets $2.36` aparece mas `XTSB鱼: folds` sumiu. O straddle discount provavelmente
alterou o `StreetState.invested` ou `max_bet` de forma que `_infer_terminal_folds` não consegue
mais identificar FishGeorge/XTSB鱼 como precisando de fold inferido.

---

## O que fazer agora — prioridade de correção

### PASSO 1 — Reverter Fix 6 imediatamente (blocker)
```python
# capture/change_detector.py, parâmetro de extract_key_frames:
min_interval_sec=0.5   # reverter de 0.25 para 0.5
```
Isso deve recuperar HL3048 de 57 → ~80 e eliminar os extras espúrios do preflop.

### PASSO 2 — Validar Fix 5 isolado (após reverter Fix 6)
Rodar o pipeline e comparar o preflop do HL3048 e o turn do HL2332:
- Se HL3048 preflop for 20/20: Fix 5 funcionou ✅
- Se HL3048 preflop regredir vs 244 (onde era 15/20): reverter Fix 5 também
- Se HL2332 turn voltar a 15/15: Fix 5 não afeta o turn ✅
- Se HL2332 turn continuar 5/15: Fix 5 quebrou `_infer_terminal_folds` → investigar

### PASSO 3 — Implementar Fix A (stack-delta → bet/raise) para HL3048 turn
**Problema**: `Hamster813: bets $5.72` aconteceu em <0.25s. Impossível capturar por frame rate.
A solução correta é inferir o bet a partir da queda de stack, sem depender de aumentar fps.

O código em `_infer_actions()` já detecta queda de stack (linhas ~361-367) mas emite `"unknown"`.
O compare_gabarito não dá crédito para `"unknown"`. Fix: classificar corretamente como `"bet"` ou `"raise"`:

```python
# engine/hand_tracker.py — _infer_actions(), bloco stack-drop existente:
elif (prev_bet < 0.05 and curr_bet < 0.05
      and prev_stack is not None and curr_stack is not None):
    stack_drop = round(prev_stack - curr_stack, 2)
    if stack_drop > 0.5:
        prev_max = state.max_bet
        if prev_max < 0.05:
            action_type = "bet"
            amount_bb   = stack_drop
        else:
            action_type = "raise"
            amount_bb   = round(stack_drop - prev_max, 2)
        state.max_bet = max(state.max_bet, stack_drop)
        state.voluntary_raises += 1
        state.last_aggressor   = sk
        state.invested[sk] = round(state.invested.get(sk, 0.0) + stack_drop, 2)
        state.has_acted.add(sk)
        action = Action(sk, name, pos, action_type, amount_bb, street, ts,
                        total_bb=state.invested[sk])
        actions.append(action)
```

**Efeito esperado**: `Hamster813: bets $5.72` aparece no turn via stack delta → turn[2] ✓
`_infer_terminal_folds` então infere `FishGeorge: folds` automaticamente → turn[3] ✓

### PASSO 4 — Implementar Fix B (just_transitioned flag) para HL3048 turn[1]
**Problema**: No frame logo após virar o turn, o chip residual do FishGeorge do flop ainda
está sendo animado para o pot. `_infer_actions` vê o chip desaparecer e emite fold falso.

O código já pula o **frame de transição** (`is_new_street=True → new_actions=[]`), mas a
animação de sweep acontece no frame **seguinte** à transição.

**Fix**: Campo `just_transitioned: bool = False` no `StreetState`. Setar `True` ao resetar
para nova rua. Em `_infer_actions`, pular fold detection quando flag estiver ativo.

```python
# 1) Adicionar ao dataclass StreetState:
just_transitioned: bool = False

# 2) Em process_sequence(), após resetar StreetState para nova rua:
new_ss.just_transitioned = True

# 3) Em _infer_actions(), antes do loop de assentos:
just_trans = state.just_transitioned
state.just_transitioned = False  # limpa — vale só 1 frame

# 4) No bloco de fold (elif prev_bet > 0.05 and curr_bet < 0.05):
if just_trans:
    continue  # chip sendo varrido pela animação — não é fold
```

**Efeito esperado**: `FishGeorge: checks` turn[1] não vira fold falso ✓
Com Fix A + Fix B + `_infer_terminal_folds` existente: turn completo 0/15 → 15/15

---

## Score alvo após Passos 1-4

| Mão | Atual (221) | Esperado pós fix | Limitação |
|-----|-------------|-----------------|-----------|
| HL4017 | 84 | **84** | Teto — gabarito com erro no preflop |
| HL3048 | 57 | **~96** | Calls $0.20 off (aceito) |
| HL2332 | 80 | **~90** | Investigar Fix 5 impacto no turn |
| **TOTAL** | **221** | **~270** | |

---

## Critério de sucesso
- Total ≥ 270/300
- HL4017 = 84/100 (teto confirmado)
- HL3048 ≥ 90/100
- HL2332 ≥ 88/100
- Nenhuma mão pode regredir vs run 244/300 (output hands_*_205149.txt)
- Todos os testes passando: `python -m pytest tests/ -q` (87 testes, 0.62s)

---

## Erros aceitos (NÃO corrigir)
- **HL4017 preflop fold order**: gabarito tem `dLzinN: folds` duplicado — erro no gabarito
- **HL3048 calls $0.20 off** ($1.58 vs $1.38): diferença de contabilidade de antes
- **Hero card suits**: highlight dourado do GGPoker impede detecção de naipe
- **Nome truncado** `我是真` vs `我是真菜.…`: limitação do OCR com nomes longos
