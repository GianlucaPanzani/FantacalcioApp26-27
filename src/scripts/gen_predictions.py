from math import isfinite
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
    predict,
    get_team_impact_score
)


def merge(model_prediction: float, team_score: float, feature: str, max_team_adjustment: float = 0.15) -> float:
    """
    Adjust a player prediction using the strength of their team.

    The adjustment is multiplicative and limited by
    `max_team_adjustment`. Positive team strength improves attacking
    and clean-sheet predictions while reducing goals conceded and
    expected defensive actions.

    Unknown features and minutes are left unchanged.
    Negative results are clamped to zero.
    """
    prediction = float(model_prediction)

    if not isfinite(prediction):
        return prediction

    directions = {
        "goals_per90": 1.0,
        "assists_per90": 1.0,
        "clean_sheets_per90": 1.0,
        "goals_against_per90": -1.0,
        "tackles_won_per90": -1.0,
        "minutes": 0.0,
    }

    direction = directions.get(feature, 0.0)
    team_score = max(-1.0, min(1.0, float(team_score)))

    adjustment = direction * max_team_adjustment * team_score
    result = max(0.0, prediction * (1 + adjustment))

    if feature == "clean_sheets_per90":
        return min(1.0, result)

    return result


def main():
    prefix_path = "../data/csv/notebooks_generated"
    players_history = load_dataset(f"{prefix_path}/serie_a_players_history.csv")
    fanta_players = load_dataset(f"{prefix_path}/Listone_Fantacalcio_Stagione_2026_27.csv")
    teams_history = load_dataset(f"{prefix_path}/serie_a_teams_history.csv")
    
    models_packages_dict = load_models(features_to_predict_list)

    # DataFrame which will contain the predictions
    predicted_fanta_players: pd.DataFrame = fanta_players.copy()

    # Initialization with NaN values
    for feature in features_to_predict_list:
        predicted_fanta_players[f"pred_{feature}"] = float("nan")

    history_by_player_id_dict: dict = {
        player_id: player_history
        for player_id, player_history in players_history.groupby("id", sort=False)
    }

    # Perform the predictions
    for player_index, fanta_player in fanta_players.iterrows():
        player_history = history_by_player_id_dict[fanta_player["Id"]]
        team = fanta_player["Squadra"]

        if player_history is None:
            continue

        fanta_role = fanta_player["R"]
        for feature in features_to_predict_per_role_dict[fanta_role]:
            model_input = build_temporal_player_input(
                player_history=player_history,
                features=models_packages_dict[feature]["features"],
            )
            model_prediction = predict(
                model_package=models_packages_dict[feature],
                player_history=model_input,
            )
            
            prediction = merge(
                model_prediction=float(model_prediction),
                team_score=get_team_impact_score(teams_history, team),
                feature=feature
            )

            predicted_fanta_players.at[player_index, f"pred_{feature}"] = float(prediction)

    # Store env and dataset
    store_env(
        data_dict={"predicted_fanta_players_df_key": predicted_fanta_players},
        path=".env",
    )
    predicted_fanta_players.to_csv("data/csv/models_generated/predicted_fanta_players_with_teams.csv", index=False)

    return


if __name__ == "__main__":
    main()
