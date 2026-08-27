# Perché scaricare quest'app

...

# Descrizione app

...

# Descrizione del Dataset

Il dataset contiene una riga per ogni combinazione **giocatore–stagione–squadra**. Le statistiche con suffisso `_per90` sono normalizzate rispetto alle frazioni da 90 minuti giocate e permettono confronti più corretti tra calciatori con minutaggi differenti.

## Identificazione e contesto

- `season` → Stagione sportiva a cui si riferiscono i dati, nel formato `YYYY-YY` (es. `2025-26`).
- `player` → Nome completo o nome identificativo del giocatore.
- `team` → Squadra di appartenenza del giocatore nella stagione indicata.
- `competition` → Campionato nel quale sono state registrate le statistiche.
- `nationality` → Nazionalità o codice della nazionale del giocatore.
- `position` → Posizione principale o insieme delle posizioni ricoperte (`GK`, `DF`, `MF`, `FW`).
- `age` → Età del giocatore nella stagione considerata.
- `birth_year` → Anno di nascita del giocatore.

## Presenze e minutaggio

- `appearances` → Numero di partite nelle quali il giocatore è sceso in campo.
- `starts` → Numero di partite iniziate da titolare.
- `minutes` → Minuti complessivamente giocati.
- `nineties` → Minuti giocati espressi come numero di frazioni da 90 minuti (`minutes / 90`).

## Produzione offensiva

- `goals_per90` → Gol segnati ogni 90 minuti.
- `assists_per90` → Assist realizzati ogni 90 minuti.
- `goals_assists_per90` → Somma di gol e assist ogni 90 minuti.
- `non_penalty_goals_per90` → Gol non segnati su rigore ogni 90 minuti.
- `non_penalty_goals_assists_per90` → Somma di gol non su rigore e assist ogni 90 minuti.
- `penalty_attempts_per90` → Rigori calciati ogni 90 minuti.

## Tiro

- `shots_on_target_pct` → Percentuale dei tiri totali terminati nello specchio della porta.
- `shots_per90` → Tiri effettuati ogni 90 minuti.
- `shots_on_target_per90` → Tiri nello specchio effettuati ogni 90 minuti.
- `goals_per_shot` → Gol segnati divisi per il numero totale di tiri; misura l'efficienza realizzativa.
- `goals_per_shot_on_target` → Gol segnati divisi per i tiri nello specchio; misura la conversione dei tiri indirizzati in porta.

## Disciplina

- `yellow_cards_per90` → Cartellini gialli ricevuti ogni 90 minuti.
- `red_cards_per90` → Cartellini rossi ricevuti ogni 90 minuti.

## Contributo difensivo

- `interceptions_per90` → Intercettazioni effettuate ogni 90 minuti.
- `tackles_won_per90` → Contrasti vinti ogni 90 minuti.

## Statistiche dei portieri

Questi campi assumono normalmente valore mancante (`NaN`) per i giocatori di movimento.

- `goals_against_per90` → Gol subiti dal portiere ogni 90 minuti.
- `shots_on_target_against_per90` → Tiri nello specchio affrontati ogni 90 minuti.
- `saves_per90` → Parate effettuate ogni 90 minuti.
- `save_pct` → Percentuale di tiri nello specchio parati.
- `wins_per90` → Vittorie maturate con il portiere in campo ogni 90 minuti giocati.
- `draws_per90` → Pareggi maturati con il portiere in campo ogni 90 minuti giocati.
- `losses_per90` → Sconfitte maturate con il portiere in campo ogni 90 minuti giocati.
- `clean_sheets_per90` → Clean sheet, cioè partite senza gol subiti, normalizzati ogni 90 minuti.
- `clean_sheet_pct` → Percentuale di presenze da portiere concluse senza subire gol.
- `keeper_penalty_attempts_per90` → Rigori affrontati dal portiere ogni 90 minuti.
- `penalties_allowed_per90` → Rigori trasformati dagli avversari ogni 90 minuti.
- `penalties_saved_per90` → Rigori parati ogni 90 minuti.
- `penalties_missed_per90` → Rigori affrontati ma calciati fuori o sui legni ogni 90 minuti; non sono parate del portiere.

## Note interpretative

- I valori `_per90` misurano una frequenza, non il contributo complessivo nell'intera stagione.
- Per evitare risultati instabili, le statistiche per 90 minuti dovrebbero essere valutate insieme a `minutes` o applicando una soglia minima di minutaggio.
- `goals_per_shot` e `goals_per_shot_on_target` sono rapporti per tiro e non statistiche per 90 minuti.
- `save_pct`, `clean_sheet_pct` e `shots_on_target_pct` sono percentuali espresse su scala 0–100.
- Le denominazioni di squadre, giocatori, nazionalità e competizioni possono richiedere una normalizzazione testuale prima di collegare il dataset ad altre fonti.
