import pandas as pd

from lib.streamlit_api import (
    load_dataset,
    load_models,
    store_env
)
from lib.xgboost_predictor import (
    build_temporal_player_input,
    features_to_predict_list,
    features_to_predict_per_role_dict,
    predict
)


def main():
    history_players = load_dataset("data/csv/filtered_history_players.csv")
    fanta_players = load_dataset("data/csv/Listone_Fantacalcio_Stagione_2026_27.csv")
    models_packages_dict = load_models(features_to_predict_list)

    # Add the new prediction columns
    predicted_fanta_players: pd.DataFrame = fanta_players.copy()
    for feature in features_to_predict_list:
        predicted_fanta_players[f"pred_{feature}"] = float("nan")

    history_by_player_id = {
        player_id: player_history
        for player_id, player_history in history_players.groupby("id", sort=False)
    }

    # Perform the predictions
    for player_index, fanta_player in fanta_players.iterrows():
        player_history = history_by_player_id.get(fanta_player["Id"])
        if player_history is None:
            continue

        fanta_role = fanta_player["R"]
        for feature in features_to_predict_per_role_dict[fanta_role]:
            model_input = build_temporal_player_input(
                player_history=player_history,
                features=models_packages_dict[feature]["features"],
            )
            prediction = predict(
                model_package=models_packages_dict[feature],
                player_history=model_input,
            )
            predicted_fanta_players.at[player_index, f"pred_{feature}"] = float(prediction)

    # Store env and dataset
    store_env(
        data_dict={"predicted_fanta_players_df_key": predicted_fanta_players},
        path=".env",
    )
    predicted_fanta_players.to_csv("data/csv/predicted_fanta_players.csv", index=False)

    return


if __name__ == "__main__":
    main()
