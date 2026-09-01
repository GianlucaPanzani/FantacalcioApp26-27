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