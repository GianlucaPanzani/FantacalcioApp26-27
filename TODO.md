# Pages

## Statistics page
- togliere tabella
- mettere selezione del numero di giocatori di cui fare il confronto nella sidebar (number_input)
- creare dinamicamente 1 col per numero inserito con un player selectbox su tutti i players
- fare l'union delle features di cui fare i plot
- passarle singolarmente (per colonna) al plot del singolo player (probabilmente eliminare la funzione plot_comparison)

## Fantacalcio page
- Invece che far caricare di volta in volta ad ogni selezione delle predictions, calcolarle prima e aggiornare la features_to_predict_per_role_dict affinche possano essere generate statistiche multiple per ogni feature (e.g. goals_per90 puo diventare sia goals per season che goals per minutes range).
- rendere la visualizzazione dei giocatori comprati piu compatte (o per singolo ruolo)

## Selection page
- caricare file creato e usare pd.concat per attaccarlo sia a quello dei players da selezionare che a quello delle selezioni effettuate

## Settings page
- Aggiungere la personalizzazione del testo affiancato alle icone del campo _interest_.


# Futuri updates
- usare un dataset storico delle aste per addestrare anche sulla predizione dei prezzi.
