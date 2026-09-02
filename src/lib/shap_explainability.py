import time
import numpy as np
import pandas as pd


def get_shap_info(shap_values_dict: dict[str, float], df: pd.DataFrame, top_k=None):
    ''''
    Get the top_k features with the highest absolute SHAP values and their corresponding explanations.

    Returns
    --------
    dict: A dictionary containing the features as keys and a dictionary of informations as values. 
        Its format is as follows:
        {
            "feature_name": {
                "value": feature_value,
                "impact": shap_value,
                "outcome": "positive" or "negative"
            }
        }
    '''
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

    explanations_by_feature_df = features_explainability.set_index("feature")
    current_year = time.localtime().tm_year

    text_md = "**_Reasoning of the model_**:\n"
    for i, (feature, shap_dict) in enumerate(shap_info_dict.items()):
        if i+1 > top_k and i < len(shap_info_dict) - worst_k:
            continue
        real_feature, years_ago = str(feature).split("_t-")
        current_year = time.localtime().tm_year
        season = f"{str(current_year - int(years_ago))}-{str(current_year)[2:]}"
        explanation_row = explanations_by_feature_df.loc[real_feature]

        symbol = ":green[⬆]" if shap_dict["outcome"] == "positive" else ":blue[⬇]"
        explanation = explanation_row[shap_dict["outcome"]]
        feature_name = f"{explanation_row['name']} ({season})"
        
        text_md += f"- {symbol} :blue[**{feature_name}**]: {explanation}\n"

    return text_md