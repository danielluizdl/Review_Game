# Referência: Formato PokerStars Hand History

Guia completo de todas as situações possíveis numa mão e o que escrever em cada uma.
Usado pelo pipeline `hh_writer_ps.py` e como referência para validação dos gabaritos.

---

## Estrutura geral de uma mão

```
[1] HEADER
[2] LISTA DE ASSENTOS
[3] ANTES
[4] BLINDS / STRADDLE
[5] *** HOLE CARDS ***
[6] AÇÕES PRÉ-FLOP
[7] *** FLOP *** (se houver)
[8] AÇÕES DO FLOP
[9] *** TURN *** (se houver)
[10] AÇÕES DO TURN
[11] *** RIVER *** (se houver)
[12] AÇÕES DO RIVER
[13] UNCALLED BET (se o último agressor não for chamado)
[14] COLETA DO POTE
[15] *** SHOW DOWN *** (se houver)
[16] *** SUMMARY ***
[linha em branco separando mãos]
```

---

## [1] Header

```
PokerStars Hand #HANDID: Hold'em No Limit ($SB/$BB/$STR(ANTE)) - YYYY/MM/DD HH:MM:SS ET
Table 'HL0000' 8-max Seat #N is the button
```

**Variações do stakes:**
| Situação | Formato |
|----------|---------|
| Com straddle e ante | `($0.05/$0.10/$0.20(0.05))` |
| Sem straddle, com ante | `($0.05/$0.10(0.05))` |
| Sem straddle, sem ante | `($0.05/$0.10)` |

---

## [2] Lista de assentos

```
Seat 1: PlayerName ($STACK in chips)
Seat 2: PlayerName ($STACK in chips)
...
```

- Apenas assentos **ocupados** aparecem (sem Empty Seat)
- Stacks em **valor real** (BB × stack_em_BB)
- Ordem crescente de assento (1→8)

---

## [3] Antes

```
PlayerName: posts the ante $0.05
```

- **Todos os jogadores** postam ante, em ordem crescente de assento
- Mesmo quem vai foldar logo em seguida

---

## [4] Blinds e Straddle

```
PlayerName: posts small blind $0.05
PlayerName: posts big blind $0.10
PlayerName: posts straddle $0.20
```

- Sempre nesta ordem: SB → BB → STR
- STR só aparece se houver straddle obrigatório na mesa

---

## [5] HOLE CARDS

```
*** HOLE CARDS ***
Dealt to Hero [Ah Kd]
```

- Só aparece para o **Hero** (jogador da perspectiva do vídeo)
- Se Hero não tiver cartas detectadas: linha `Dealt to Hero` **omitida** (não escrevemos `Dealt to Hero []`)
- Naipes são placeholder quando não detectáveis (limitação do GGPoker com highlight dourado)

---

## [6–12] Ações por rua

### Ações possíveis

| Ação | Formato |
|------|---------|
| Fold | `PlayerName: folds` |
| Check | `PlayerName: checks` |
| Call | `PlayerName: calls $AMOUNT` |
| Bet | `PlayerName: bets $AMOUNT` |
| Raise | `PlayerName: raises $RAISE_AMT to $TOTAL` |
| All-in fold | `PlayerName: folds` *(igual ao fold normal)* |
| All-in call | `PlayerName: calls $AMOUNT and is all-in` |
| All-in bet | `PlayerName: bets $AMOUNT and is all-in` |
| All-in raise | `PlayerName: raises $RAISE_AMT to $TOTAL and is all-in` |

**Exemplo de raise:**
```
Hamster813: raises $0.55 to $0.75
```
→ `$0.55` = incremento acima da aposta anterior | `$0.75` = total colocado nessa rua

**Exemplo de all-in:**
```
PlayerName: raises $8.00 to $10.00 and is all-in
```

---

## Seções de cartas comunitárias

### Flop
```
*** FLOP *** [Card1 Card2 Card3]
```

### Turn
```
*** TURN *** [Card1 Card2 Card3] [Card4]
```
→ repete os 3 do flop entre `[]` e adiciona a 4ª entre `[]` separado

### River
```
*** RIVER *** [Card1 Card2 Card3] [Card4] [Card5]
```
→ repete flop, depois turn, depois river, cada grupo entre `[]` separado

**Mão com todas as ruas:**
```
*** FLOP *** [Jd 5s 2h]
easycall86: checks
taymonkha: checks
*** TURN *** [Jd 5s 2h] [3d]
easycall86: checks
taymonkha: checks
*** RIVER *** [Jd 5s 2h] [3d] [7s]
easycall86: checks
taymonkha: checks
```

**Mão encerrada no turn (ninguém viu o river):**
```
*** FLOP *** [Kd Ad 9d]
...
*** TURN *** [Kd Ad 9d] [8d]
FishGeorge: folds
Uncalled bet ($5.72) returned to Hamster813
Hamster813 collected $11.38 from pot
```
→ não escreve `*** RIVER ***`

**Mão encerrada no flop:**
```
*** FLOP *** [5h Qs 8d]
XTSB鱼: checks
dLzinN: bets $0.92
XTSB鱼: folds
Uncalled bet ($0.92) returned to dLzinN
dLzinN collected $X from pot
```

**Mão encerrada pré-flop (todos foldaram):**
```
*** HOLE CARDS ***
...todas as ações pré-flop...
Uncalled bet ($1.90) returned to PlayerName
PlayerName collected $X from pot
PlayerName: doesn't show hand
*** SUMMARY ***
```
→ nenhuma seção de rua aparece

---

## [13] Uncalled bet

Aparece quando **o último agressor não é chamado** (todos foldaram):

```
Uncalled bet ($AMOUNT) returned to PlayerName
```

- `AMOUNT` = valor apostado que não teve chamada
- Vem ANTES de `PlayerName collected ...`
- O valor coletado = pot total − uncalled bet

**Exemplo:**
```
Hamster813: bets $5.72
FishGeorge: folds
Uncalled bet ($5.72) returned to Hamster813
Hamster813 collected $11.38 from pot
```

**Quando NÃO aparece:** se a aposta foi chamada (call), o valor não é devolvido.

---

## [14] Coleta do pote

### Vencedor único
```
PlayerName collected $AMOUNT from pot
```

### Dois potes (all-in com side pot)
```
PlayerName collected $AMOUNT from main pot
PlayerName collected $AMOUNT from side pot
```

### Split pot (empate)
```
PlayerName collected $AMOUNT from pot
PlayerName collected $AMOUNT from pot
```

---

## [15] SHOW DOWN

Aparece quando **pelo menos um jogador mostra as cartas** (chegou ao showdown ou foi obrigado a mostrar).

### Jogador mostra as cartas
```
*** SHOW DOWN ***
PlayerName: shows [Card1 Card2] (hand description)
```

### Jogador não mostra (muckou)
```
PlayerName: mucks hand
```

### Jogador coletou sem mostrar
```
PlayerName: doesn't show hand
```

**Quando aparece `*** SHOW DOWN ***`:**
- River foi até o final COM pelo menos 2 jogadores ativos → todos mostram
- Vencedor no river após bet/call (adversário pode muckar)
- Nunca em mãos encerradas pré-flop ou que não chegaram ao showdown

**Exemplo completo de showdown:**
```
*** SHOW DOWN ***
taymonkha: shows [Ac Td] (high card Ace - Ten kicker)
easycall86: shows [Ah 8c] (high card Ace)
taymonkha collected $2.15 from pot
```

**Hero ganhou e mostrou (no show down):**
```
*** SHOW DOWN ***
dLzinN: shows [Ah Ad] (a pair, Aces)
```

**Hero coletou mas não chegou ao showdown:**
```
dLzinN collected $4.71 from pot
dLzinN: doesn't show hand
```

---

## [16] SUMMARY

```
*** SUMMARY ***
Total pot $AMOUNT | Rake $0.00
Board [Card1 Card2 Card3 Card4 Card5]
Seat N: PlayerName (ROLE) OUTCOME
```

### Board no summary

| Situação | Board |
|----------|-------|
| Mão encerrada pré-flop | *(sem linha Board)* |
| Só flop jogado | `Board [C1 C2 C3]` |
| Flop + turn | `Board [C1 C2 C3 C4]` |
| Flop + turn + river | `Board [C1 C2 C3 C4 C5]` |

### ROLE entre parênteses

| Posição | Formato |
|---------|---------|
| Button | `(button)` |
| Small Blind | `(small blind)` |
| Big Blind | `(big blind)` |
| Straddle | `(straddle)` |
| Outros (UTG, HJ, CO) | *(sem role)* |

### OUTCOME por situação

| Situação | Formato |
|----------|---------|
| Foldou pré-flop sem apostar | `folded before Flop (didn't bet)` |
| Foldou pré-flop após apostar/call | `folded before Flop` |
| Foldou no flop | `folded on the Flop` |
| Foldou no turn | `folded on the Turn` |
| Foldou no river | `folded on the River` |
| Coletou o pote | `collected ($AMOUNT)` |
| Coletou e mostrou cartas | `showed [C1 C2] and won ($AMT) with HAND` |
| Perdeu no showdown | `showed [C1 C2] and lost with HAND` |
| Muckou no showdown | `mucked [C1 C2]` |

### Exemplos de SUMMARY completo

**Mão sem board (encerrada pré-flop):**
```
*** SUMMARY ***
Total pot $4.81 | Rake $0.00
Seat 1: dLzinN folded before Flop (didn't bet)
Seat 7: 我是真 collected ($4.81)
```

**Mão com board parcial + winner:**
```
*** SUMMARY ***
Total pot $11.38 | Rake $0.00
Board [Kd Ad 9d 8d]
Seat 2: Hamster813 collected ($11.38)
Seat 7: Andylau408 (straddle) folded on the Flop
Seat 8: FishGeorge folded on the Turn
```

**Mão com showdown:**
```
*** SUMMARY ***
Total pot $2.15 | Rake $0.00
Board [Jd 5s 2h 3d 7s]
Seat 4: easycall86 (straddle) showed [Ah 8c] and lost with high card Ace
Seat 5: taymonkha collected ($2.15) showed [Ac Td] and won ($2.15) with high card Ace
```

---

## Casos especiais importantes

### Mão encerrada pré-flop sem nenhuma aposta (só folds)
Não há `Uncalled bet`. O BB coleta diretamente:
```
*** HOLE CARDS ***
PlayerA: folds
PlayerB: folds
[todos foldaram exceto o BB]
BB_Player collected $0.35 from pot
BB_Player: doesn't show hand
*** SUMMARY ***
Total pot $0.35 | Rake $0.00
```

### Jogador que foldou antes do flop MAS apostou algo
```
Seat 5: 打不赢不 (button) folded before Flop
```
→ sem `(didn't bet)` porque ele apostou/chamou antes de foldar

### Jogador que foldou antes do flop sem apostar nada
```
Seat 6: nianian folded before Flop (didn't bet)
```

### Seat com stack $0.00 (jogador esperando)
Aparece na lista de assentos, posta ante normalmente:
```
Seat 6: chipboiz ($0.00 in chips)
chipboiz: posts the ante $0.05
```

### Total pot vs. valor coletado
```
Total pot $7.07 | Rake $0.00
dLzinN collected $4.71 from pot   ← pot - uncalled bet
```
→ `Total pot` = tudo que entrou no pote (incluindo aposta não chamada)
→ `collected` = total pot − uncalled bet

---

## Ordem de ocorrência das seções (resumo visual)

```
Header
Assentos
Antes (todos)
SB / BB / STR
*** HOLE CARDS ***
  Dealt to Hero [cartas]
  [ações pré-flop]
[se houve flop:]
  *** FLOP *** [3 cartas]
  [ações flop]
[se houve turn:]
  *** TURN *** [3 cartas] [1 carta]
  [ações turn]
[se houve river:]
  *** RIVER *** [3 cartas] [1 carta] [1 carta]
  [ações river]
[se último agressor não foi chamado:]
  Uncalled bet ($X) returned to PlayerName
[coleta:]
  PlayerName collected $X from pot
[se showdown:]
  *** SHOW DOWN ***
  PlayerName: shows [cartas] (descrição)
  PlayerName: mucks hand  OU  doesn't show hand
*** SUMMARY ***
  Total pot $X | Rake $0.00
  Board [cartas]  (se houve board)
  Seat N: PlayerName (role) outcome
[linha em branco]
```
