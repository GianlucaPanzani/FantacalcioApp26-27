import time
import numpy as np
import pandas as pd


def get_shap_info(shap_values_dict: dict[str, float], df: pd.DataFrame, top_k=None):
    """Return the features with the greatest absolute SHAP impact.

    Params
    ----------
    shap_values_dict : dict of str to float
        SHAP impact indexed by model feature.
    df : pandas.DataFrame
        One-row model input containing the corresponding feature values.
    top_k : int or None
        Maximum number of features to include; all features when omitted.

    Returns
    --------
    dict
        Feature values, signed impacts and positive/negative outcomes.
    """
    feature_shap_value_list = [(k, abs(v)) for k, v in shap_values_dict.items()]
    feature_shap_value_list.sort(key=lambda x: x[1], reverse=True)

    if top_k is None:
        top_k = len(feature_shap_value_list)

    top_features = [c for c, v in feature_shap_value_list[:top_k]]

    pred_exp_dict = {}
    for col in top_features:
        value = df[col].iloc[0]
        shap_value = shap_values_dict[col]

        pred_exp_dict[col] = {
            "value": value,
            "impact": round(shap_value, 2),
            "outcome": "positive" if shap_value > 0 else "negative"
        }
    return pred_exp_dict


def build_model_explaination_response(
        shap_explainer,
        features: list,
        features_explainability: pd.DataFrame,
        player_history: pd.DataFrame,
        top_k=3,
        worst_k=2
    ) -> str:
    """Build a Markdown explanation from a model's SHAP values.

    Params
    ----------
    shap_explainer : object
        SHAP explainer exposing a ``shap_values`` method.
    features : list
        Ordered model features used to build the input row.
    features_explainability : pandas.DataFrame
        Human-readable positive and negative explanations per feature.
    player_history : pandas.DataFrame
        Temporal model input for the selected player.
    top_k : int
        Number of strongest positive or negative features to include first.
    worst_k : int
        Number of lowest-ranked features to include.

    Returns
    -------
    str
        Markdown list explaining the most relevant model signals.
    """

    available_features = set(
        player_history.attrs.get("available_features", features)
    )
    seasons_by_lag = player_history.attrs.get("seasons_by_lag", {})

    # Get the first player with the passed features
    player = player_history[features].iloc[0]
    X_input = player.to_frame().T

    # Explainability with SHAP
    shap_values = shap_explainer.shap_values(X_input)
    if getattr(shap_values, "ndim", 1) > 1:
        shap_values = shap_values[0]
    shap_info_dict = get_shap_info(
        shap_values_dict=dict(zip(X_input.columns, shap_values)),
        df=X_input,
    )
    shap_info_dict = {
        feature: shap_dict
        for feature, shap_dict in shap_info_dict.items()
        if feature in available_features
    }

    explanations_by_feature_df = features_explainability.set_index("feature")

    text_md = "**_Reasoning of the model_**:\n"
    for i, (feature, shap_dict) in enumerate(shap_info_dict.items()):
        if i+1 > top_k and i < len(shap_info_dict) - worst_k:
            continue
        real_feature, years_ago = str(feature).split("_t-")
        lag = int(years_ago)
        season = seasons_by_lag.get(lag)
        if season is None:
            current_year = time.localtime().tm_year
            season = f"{str(current_year - lag)}-{str(current_year)[2:]}"
        explanation_row = explanations_by_feature_df.loc[real_feature]

        symbol = ":green[⬆]" if shap_dict["outcome"] == "positive" else ":blue[⬇]"
        explanation = explanation_row[shap_dict["outcome"]]
        feature_name = f"{explanation_row['name']} ({season})"
        
        text_md += f"- {symbol} :blue[**{feature_name}**]: {explanation}\n"

    return text_md
