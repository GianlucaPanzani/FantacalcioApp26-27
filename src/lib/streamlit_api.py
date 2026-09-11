import base64
from io import BytesIO
import mimetypes
import joblib
from numbers import Integral, Real
from pathlib import Path
import altair as alt
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
import streamlit as st
from lib.utils import (
    columns_to_user_view_dict,
    stats_persistent_key_fields,
    get_color_per_role,
    get_condition_by,
    get_default_value,
    get_ai_icon,
    ai_data_stream
)
from lib.shap_explainability import (
    build_model_explaination_response,
)
from lib.xgboost_predictor import (
    build_temporal_player_input,
    predict,
    get_transformed_feature_and_value,
    features_to_predict_per_role_dict
)



@st.cache_data(show_spinner=False)
def load_dataset(path: str, filter_by_current_year: bool = False, current_season: str = "2026-27") -> pd.DataFrame:
    """Load and cache a players dataset."""
    df = pd.read_csv(path, low_memory=False)
    return df.loc[df["season"].eq(current_season)].copy() if filter_by_current_year else df


@st.cache_resource
def load_models(target_features: list) -> dict:
    '''
    Returns
    -------
    - dict:
        Dictionary containing one entry for each target feature.

        Structure::
            {
                "target_feature1": {
                    "model": model,
                    "explainer": explainer,
                    "features": features,
                    "window_size": window_size,
                    "RMSE": rmse_error,
                    "MAE": baseline_error
                },

                "target_feature2": {
                    ...
                },
            }
    '''
    models_packages_dict = {}
    for feature in target_features:
        models_packages_dict[feature] = joblib.load(f"models/xgb_{feature}.pkl")
    return models_packages_dict


def bottom_caption():
    st.space(100)
    with st.bottom:
        st.caption("© 2026 GP · All rights reserved")
    return


def set_page_background(image_path: str | Path):
    image_path = Path(image_path)
    if not image_path.is_file():
        raise FileNotFoundError(f"Background image not found: {image_path}")

    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")

    return st.html(
        f"""
        <style>
        [data-testid="stAppViewContainer"] {{
            background-image:
                linear-gradient(rgba(0, 0, 0, 0.35), rgba(0, 0, 0, 0.35)),
                url("data:{mime_type};base64,{encoded_image}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}
        </style>
        """
    )


def set_dark_background():
    return st.html(
        f"""
        <style>
        [class*="st-key-dark-card-"] {{
            background-color: rgba(14, 17, 23, 0.94);
            border-radius: 0.75rem;
            padding: 1rem;
        }}
        </style>
        """
    )


def apply_filters(df: pd.DataFrame, exclude=None, columns_to_filter_list=[], compare_op_for_columns_to_filter_dict={}, page="unknown_page") -> pd.DataFrame:
    """Apply session-state filters, excluding one filter when requested."""
    result = df.copy()

    for column in columns_to_filter_list:
        selected_values = st.session_state.get(f"{page}_{column}_key", get_default_value(result[column]))
        if exclude == column or not selected_values:
            continue
        result = result[
            get_condition_by(result, column, selected_values, compare_op_for_columns_to_filter_dict[column])
        ]

    return result


def set_text_size(text_size, class_name):
    return st.html(
        f"""
        <style>
        [class*="{class_name}"] [data-testid="stMetricLabel"] p {{
            font-size: {str(text_size)}rem;
        }}
        </style>
        """
    )


def print_ai_icon_with_markdown_title(markdown_text = f"### AI predictions"):
    cols = st.columns([1,19])
    with cols[0]:
        st.markdown(f"{get_ai_icon()}")
    with cols[1]:
        st.markdown(markdown_text)


def print_models_predictions(
        models_packages_dict: dict,
        history_players: pd.DataFrame,
        history_of_the_player: pd.DataFrame,
        player_row: pd.Series,
        top_k=5,
        worst_k=2,
        explainability_enabled=True,
        plots_enebled=True
    ):
    features_explainability = load_dataset("data/csv/ai_models_generated/features_explainability.csv")
    role_column_means = compute_role_column_means(history_players)

    print_ai_icon_with_markdown_title(markdown_text=f"### AI predictions")

    with st.container():
        col1, _, col2 = st.columns([9,1,40])

        # Create Fanta player title
        player_name = player_row["player"]
        fanta_role = player_row["fanta_role"]
        role_name = get_roles_dict()[fanta_role].capitalize()
        latest_team = player_row["Squadra"]
        role_badge_color = get_color_per_role(role=fanta_role, color_version=False)

        with col1:
            with st.container(border=True, horizontal_alignment="center", width="stretch", key=f"dark-card-{player_name}_col1"):
                st.markdown(
                    f"### :material/person: {player_name}",
                    text_alignment="center",
                )
                st.markdown(
                    f":{role_badge_color}-badge[{role_name} ({fanta_role})]  \n:violet-badge[{latest_team}]",
                    text_alignment="center",
                )

        with col2:

            with st.container(border=True, width="stretch", key=f"dark-card-{player_name}_col2"):
                n_iters = len(features_to_predict_per_role_dict[fanta_role])

                if explainability_enabled or plots_enebled:
                    cols = st.columns([9,1,9,1,9])
                elif n_iters <= 5:
                    cols = st.columns([9,1] * (n_iters-1) + [9])
                else:
                    cols = st.columns([9,1,9,1,9,1,9])
                    
                n_cols = len(cols) + 1

                # Predict the minutes (used to do some calculus)
                minutes_package = models_packages_dict["minutes"]
                minutes_input = build_temporal_player_input(
                    player_history=history_of_the_player,
                    features=minutes_package["features"],
                )
                predicted_minutes = float(
                    predict(
                        model_package=minutes_package,
                        player_history=minutes_input,
                    )
                )
                predicted_minutes = max(0, min(predicted_minutes, 38 * 90))

                for i, feature in enumerate(features_to_predict_per_role_dict[fanta_role]):
                    model_package = models_packages_dict[feature]

                    # Build the dataframe input for the model to get the prediction
                    model_input = build_temporal_player_input(
                        player_history=history_of_the_player,
                        features=model_package["features"],
                    )
                    available_lags = model_input.attrs["available_lags"]
                    if available_lags == 0:
                        with cols[i*2 % n_cols]:
                            st.info(f"No historical seasons available for {columns_to_user_view_dict[feature]}.")
                        continue

                    prediction = predict(
                        model_package=model_package,
                        player_history=model_input,
                    )

                    with cols[i*2 % n_cols]:

                        # AI prediction
                        mean_value = role_column_means[fanta_role][feature]
                        _, mean_transformed_value = get_transformed_feature_and_value(
                            feature=feature,
                            pred_value=mean_value,
                            pred_minutes=predicted_minutes
                        )
                        transformed_feature, tranformed_value = get_transformed_feature_and_value(
                            feature=feature,
                            pred_value=prediction,
                            pred_minutes=predicted_minutes
                        )
                        with st.container(horizontal_alignment="center", border=True if plots_enebled or explainability_enabled else False):
                            st.metric(
                                label=f"**:blue[_{transformed_feature}_]**",
                                value=f":blue[{tranformed_value:.2f}]",
                                delta=f"{tranformed_value - mean_transformed_value:+.2f} [Mean: {mean_transformed_value}]",
                                delta_color="normal",
                                width="content",
                            )

                        # Case of plot enabled
                        if plots_enebled:
                            plot_player_history(
                                history_players=load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv"),
                                player=player_name,
                                feature=feature,
                                seasons_to_plot=4,
                                disable_player_name=True,
                                models_packages_dict=models_packages_dict,
                            )

                        # Case of SHAP explainability enabled
                        st.session_state.setdefault(f"previous_explaination_for_{feature}_{player_name}", False)
                        if explainability_enabled:
                            explaination_response = build_model_explaination_response(
                                shap_explainer=model_package["explainer"],
                                features=model_package["features"],
                                features_explainability=features_explainability,
                                player_history=model_input,
                                top_k=top_k,
                                worst_k=worst_k
                            )
                            if not st.session_state[f"previous_explaination_for_{feature}_{player_name}"]:
                                st.session_state[f"previous_explaination_for_{feature}_{player_name}"] = True
                                st.write_stream(ai_data_stream(explaination_response))
                            else:
                                st.markdown(explaination_response)
                    
                        #if (explainability_enabled or plots_enebled) and i < n_iters-1 and i*2 % (n_cols/2) == 0:
                        #    st.divider()
                        #elif i > 0 and i < n_iters-1 and i*2 % (n_cols/2) == 0:
                        #    st.divider()

    return


def get_stats_persistent_keys(player_ids, page_name="stats") -> list[str]:
    """
    Build the persistent Session State keys used by the statistics tables.

    One key is created for every editable field of every player ID.
    """
    persistent_keys = []
    unique_player_ids = pd.Series(player_ids).dropna().drop_duplicates()

    for player_id in unique_player_ids:
        if isinstance(player_id, Real) and float(player_id).is_integer():
            player_id = int(player_id)

        for field in stats_persistent_key_fields:
            persistent_keys.append(f"{page_name}_{field}_{player_id}_key")

    return persistent_keys

def config_page(page_title="Fantacalcio tool", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )

def highlight_bought_rows(row, fanta_managers):
    '''Highlight bought players first, otherwise use the Fantacalcio role color.'''
    my_fanta_manager_color = "#23C43E" #"#36EB69"
    others_fanta_managers_color = "#D44633" #"#37A5FF"
    if row["bought"] == st.session_state["settings_my_manager_key"]:
        row_style = f"background-color: {my_fanta_manager_color}; color: #212121"
    elif row["bought"] in fanta_managers:
        row_style = f"background-color: {others_fanta_managers_color}; color: #212121"
    else:
        role_color = get_color_per_role(row.get("fanta_role", ""))
        row_style = (
            f"background-color: {role_color}; color: #212121"
            if role_color
            else ""
        )
    return [row_style] * len(row)

def sidebar_navigation_size(font_size=1.15, font_weight=600):
    return st.html(
        f"""
        <style>
        [data-testid="stSidebarNavLink"] span {{
            font-size: {font_size}rem;
            font-weight: {font_weight};
        }}
        </style>
        """
    )

def thick_divider(height=4, border="none", background_color="#808080", border_radius=4, margin=20):
    return st.html(
        f"""
        <hr style="
            height: {str(height)}px;
            border: {str(border)};
            background-color: {str(background_color)};
            border-radius: {border_radius}px;
            margin: {str(margin)}px 0;
        ">
        """
    )

def toast_css_format(background_color="#47BEF1", border_color="#FFFFFF", border_size=2):
    return st.html(
        f"""
        <style>
        [data-testid="stToast"] {{
            background-color: {background_color};
            border: {border_size}px solid {border_color};
            box-shadow: 0 4px 14px rgba(255, 179, 0, 0.35);
        }}

        [data-testid="stToast"] * {{
            color: #664D03 !important;
        }}
        </style>
        """
    )

def get_user_view_of_column(col: str):
    return columns_to_user_view_dict.get(col, col.replace("_", " ").capitalize())

def get_col_from_user_view(user_view: str):
    for col, user_view_i in columns_to_user_view_dict.items():
        if user_view == user_view_i:
            return col
    return user_view

def get_role_limits() -> dict:
    return {
        "P": st.session_state.get("settings_P_limit_key", 3),
        "D": st.session_state.get("settings_D_limit_key", 8),
        "C": st.session_state.get("settings_C_limit_key", 8),
        "A": st.session_state.get("settings_A_limit_key", 6),
    }

def get_roles_list(enable_aka=False) -> list:
    return [
        "goalkeeper" + f"{' (P)' if enable_aka else ''}",
        "defender" + f"{' (D)' if enable_aka else ''}",
        "midfielder" + f"{' (C)' if enable_aka else ''}", 
        "attacker" + f"{' (A)' if enable_aka else ''}"
    ]

def get_roles_dict() -> dict:
    '''
    { "P": "goalkeeper", "D": "defender", "C": "midfielder", "A": "attacker" }
    '''
    return {
        "P": "goalkeeper",
        "D": "defender",
        "C": "midfielder",
        "A": "attacker"
    }

def get_role_budget_limits() -> dict:
    return {
        "P": st.session_state.get("settings_P_budget_limit_key", 50),
        "D": st.session_state.get("settings_D_budget_limit_key", 100),
        "C": st.session_state.get("settings_C_budget_limit_key", 200),
        "A": st.session_state.get("settings_A_budget_limit_key", 150),
    }

def get_fanta_manager_players_dict() -> dict:
    # Case of rebuild of the bought players dict by restoring from csv
    if "fantacalcio_manager_players_dict_key" not in st.session_state:
        fanta_manager_players_dict = {}

        # Restore data from csv
        restored_players = st.session_state.get("fantacalcio_bought_players_df_key", pd.DataFrame())

        # Rebuilt of the bought players dict
        if not restored_players.empty and "manager" in restored_players.columns:
            for fanta_manager, bought_players in restored_players.groupby("manager"):
                fanta_manager_players_dict[fanta_manager] = bought_players.reset_index(drop=True)

        # Preserve Fanta Managers without bought players
        if "settings_managers_key" in st.session_state:
            fanta_managers = st.session_state["settings_managers_key"]
            for fanta_manager in fanta_managers:
                fanta_manager_players_dict.setdefault(fanta_manager, pd.DataFrame())

        st.session_state["fantacalcio_manager_players_dict_key"] = fanta_manager_players_dict

    # Case of data already present in session_state
    fanta_manager_players_dict = st.session_state["fantacalcio_manager_players_dict_key"]
    return fanta_manager_players_dict

def get_from_session_state(key: str):
    if key in st.session_state:
        return st.session_state[key]
    return None


def load_env(keys: list[str] | None = None, path: str = ".env") -> dict:
    """Load selected or all stored values into Session State."""
    env_path = Path(path)
    if not env_path.exists():
        return {}

    # Read the environment file into a dictionary.
    env_values = {}
    with env_path.open(encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            env_key, env_value = line.split("=", 1)
            env_values[env_key.strip()] = env_value.strip().strip('"').strip("'")

    if keys is None:
        keys = [key for key in env_values if not key.endswith("_type")]

    loaded_values = {}
    for key in keys:
        # Keep values already initialized during the current session.
        if key not in env_values:
            continue
        if key in st.session_state:
            loaded_values[key] = st.session_state[key]
            continue

        raw_value = env_values[key]
        value_type = env_values.get(f"{key}_type", "str")

        match value_type:
            case "str":
                value = raw_value
            case "int":
                value = int(raw_value)
            case "float":
                value = float(raw_value)
            case "bool":
                normalized_value = raw_value.lower()
                if normalized_value not in {"true", "false"}:
                    raise ValueError(f"Invalid bool value for '{key}': {raw_value}")
                value = normalized_value == "true"
            case "list":
                value = [item.strip() for item in raw_value.split(",") if item.strip()]
            case "tuple":
                value = tuple(item.strip() for item in raw_value.split(",") if item.strip())
            case "None" | "NoneType":
                value = None
            case "pd.DataFrame":
                csv_path = Path(raw_value)
                if not csv_path.is_absolute():
                    csv_path = env_path.parent / csv_path
                if not csv_path.exists():
                    continue
                value = pd.read_csv(csv_path, low_memory=False)
            case _:
                raise ValueError(f"Unsupported type for '{key}': {value_type}")

        st.session_state[key] = value
        loaded_values[key] = value

    return loaded_values


def store_env(data_dict: dict, path: str = ".env") -> dict:
    """Store supported values in an environment file."""
    env_path = Path(path)

    # Preserve values already stored in the environment file.
    env_values = {}
    if env_path.exists():
        with env_path.open(encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                env_key, env_value = line.split("=", 1)
                env_values[env_key.strip()] = env_value.strip().strip('"').strip("'")

    stored_values = {}
    for key, value in data_dict.items():
        if key.endswith("_type"):
            continue

        if isinstance(value, pd.DataFrame):
            value_type = "pd.DataFrame"
            default_name = key.removesuffix("_df_key")
            csv_value = f"data/csv/{default_name}.csv"
            if env_values.get(f"{key}_type") == "pd.DataFrame":
                csv_value = env_values[key]
            csv_path = Path(csv_value)
            if not csv_path.is_absolute():
                csv_path = env_path.parent / csv_path
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            value.to_csv(csv_path, index=False)
            stored_value = csv_value
        elif isinstance(value, str):
            value_type = "str"
            stored_value = value
        elif isinstance(value, bool):
            value_type = "bool"
            stored_value = str(value).lower()
        elif isinstance(value, Integral):
            value_type = "int"
            stored_value = str(value)
        elif isinstance(value, Real):
            value_type = "float"
            stored_value = str(value)
        elif isinstance(value, list):
            value_type = "list"
            stored_value = ",".join(str(item) for item in value)
        elif isinstance(value, tuple):
            value_type = "tuple"
            stored_value = ",".join(str(item) for item in value)
        elif value is None:
            value_type = "NoneType"
            stored_value = ""
        else:
            continue

        env_values[key] = stored_value
        env_values[f"{key}_type"] = value_type
        stored_values[key] = value

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_content = "\n".join(f"{key}={value}" for key, value in env_values.items())
    env_path.write_text(f"{env_content}\n", encoding="utf-8")

    return stored_values

def restore_bought_players(bought_players_df_key: str, settings_managers_key: str, fanta_manager_players_dict_key:str):
    '''Rebuild of the bought players dict by csv'''
    fanta_manager_players_dict = {}

    # Restore data from csv
    restored_players: pd.DataFrame = st.session_state.get(bought_players_df_key, pd.DataFrame())

    # Rebuilt of the bought players dict
    if not restored_players.empty and "manager" in restored_players.columns:
        for fanta_manager, bought_players in restored_players.groupby("manager"):
            fanta_manager_players_dict[fanta_manager] = bought_players.reset_index(drop=True)

    # Preserve Fanta Managers without bought players
    fanta_managers = st.session_state[settings_managers_key]
    for fanta_manager in fanta_managers:
        fanta_manager_players_dict.setdefault(fanta_manager, pd.DataFrame())

    st.session_state[fanta_manager_players_dict_key] = fanta_manager_players_dict


def sync_filter(filter_key: str, widget_key: str) -> None:
    """Copy a widget value into its persistent filter state."""
    st.session_state[filter_key] = st.session_state.get(widget_key)


def add_graphical_columns(graphical_cols_key, widget_key):
    st.session_state[graphical_cols_key].extend(st.session_state[widget_key])
    st.session_state[widget_key] = []


def create_player_history_chart(
        data: pd.DataFrame,
        statistic_name: str,
        y_limits=None,
        mean_value: float | None = None,
        prediction_data: pd.DataFrame | None = None,
        enable_collapse_values=False
    ):
    """Create a player history chart with season, team and value tooltips."""
    data = data.copy()
    tooltip = [
        alt.Tooltip("season:N", title="Season"),
        alt.Tooltip("team:N", title="Team"),
        alt.Tooltip("value:Q", title=statistic_name),
    ]
    if enable_collapse_values and not data.empty:
        data["value"] = pd.to_numeric(data["value"], errors="coerce")
        data = data.dropna(subset=["value"])
        data["team"] = data["team"].fillna("Unknown team")
        data["team_value"] = data.apply(
            lambda row: f"{row['team']}: {row['value']:.2f}",
            axis=1,
        )
        data = data.groupby("season", sort=False, as_index=False).agg(
            value=("value", "mean"),
            team_values=("team_value", " | ".join),
            team_count=("team", "nunique"),
        )

    y_scale = alt.Scale(zero=False)
    if y_limits is not None:
        y_scale = alt.Scale(domain=list(y_limits), zero=False)

    season_order = data["season"].drop_duplicates().tolist()
    if prediction_data is not None and not prediction_data.empty:
        for season in prediction_data["season"].drop_duplicates():
            if season not in season_order:
                season_order.append(season)

    chart = alt.Chart(data).mark_line(point=not enable_collapse_values).encode(
        x=alt.X("season:N", title="Season", sort=season_order),
        y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
    )
    if not enable_collapse_values:
        chart = chart.encode(tooltip=tooltip)

    chart_layers = [chart]

    if enable_collapse_values and not data.empty:
        single_team_points = alt.Chart(data[data["team_count"].eq(1)]).mark_point().encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title=statistic_name, format=".2f"),
                alt.Tooltip("team_values:N", title="Values by team"),
            ],
        )
        multiple_team_points = alt.Chart(data[data["team_count"].gt(1)]).mark_point().encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title=f"Average {statistic_name}", format=".2f"),
                alt.Tooltip("team_values:N", title="Values by team"),
            ],
        )
        chart_layers.extend([single_team_points, multiple_team_points])

    if mean_value is not None:
        mean_data = pd.DataFrame({"mean": [mean_value]})
        mean_line = alt.Chart(mean_data).mark_rule(
            color="#8A8A8A",
            opacity=0.75,
            strokeDash=[6, 4],
            strokeWidth=1.5,
        ).encode(
            y=alt.Y("mean:Q", scale=y_scale),
            tooltip=[alt.Tooltip("mean:Q", title="Role average", format=".2f")],
        )
        chart_layers.append(mean_line)

    if prediction_data is not None and not prediction_data.empty:
        prediction_point = alt.Chart(prediction_data).mark_point(
            color="#BE27D9",
            filled=True,
            shape="diamond",
            size=150,
        ).encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title=f"AI prediction", format=".2f"),
            ],
        )
        chart_layers.append(prediction_point)

    return alt.layer(*chart_layers)


def compute_role_column_means(history_players: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    """
    Compute numeric column means by role, giving each player equal weight.

    First average each player's historical values, then average those results
    across all players with the same role.
    """
    numeric_columns = history_players.select_dtypes(include="number").columns
    role_column_means = {}

    for role in get_roles_dict().keys():
        # Keep all historical rows for players of the requested role.
        role_players = history_players.loc[
            history_players["fanta_role"] == role,
            ["player", *numeric_columns],
        ]

        # Average each player's history, then average all players of the role.
        player_column_means = role_players.groupby("player")[numeric_columns].mean()
        role_column_means[role] = {
            column: (
                None
                if player_column_means[column].dropna().empty
                else float(player_column_means[column].mean())
            )
            for column in numeric_columns
        }

    return role_column_means


def plot_comparison_between_players(history_players: pd.DataFrame, filtered_players: pd.DataFrame) -> None:
    """
    Compare the historical statistics of two selected players.

    The statistics configured for both player roles are combined and displayed
    in the same order. The first player is shown on the left and the second one
    on the right.

    Parameters
    ----------
    filtered_players:
        DataFrame containing the historical records of two players.
    """
    roles = filtered_players["fanta_role"].dropna().unique().tolist()
    role_column_means = compute_role_column_means(history_players)

    available_players = filtered_players["player"].dropna().drop_duplicates().tolist()
    selected_players = st.session_state.get("statistics_player_key", [])
    player_names = [player for player in selected_players if player in available_players]

    # Add players missing from Session State while preserving DataFrame order.
    for player in available_players:
        if player not in player_names:
            player_names.append(player)

    # Create the cols to plot as the union of the cols of the 2 players
    columns_to_plot = []
    for player_name in player_names:
        player_df = filtered_players[filtered_players["player"] == player_name]

        fanta_role = player_df["fanta_role"].dropna().iloc[0]
        role_name = get_roles_dict()[fanta_role]
        columns = st.session_state.get(f"settings_{fanta_role}_graphical_cols_key", [])

        for col in columns:
            if col in filtered_players.columns and col not in columns_to_plot:
                columns_to_plot.append(col)

    # Keep the same readable order in both player columns
    columns_to_plot = sorted(columns_to_plot, key=lambda col: get_user_view_of_column(col).lower())

    # Calculate the common Y-axis limits for each statistic.
    y_limits_dict = {}
    for col in columns_to_plot:
        player_min_values = []
        player_max_values = []

        for player_name in player_names:
            player_df = filtered_players[filtered_players["player"] == player_name]
            player_values = player_df[col]
            player_values = pd.to_numeric(player_values, errors="coerce").dropna()

            if not player_values.empty:
                player_min_values.append(float(player_values.min()))
                player_max_values.append(float(player_values.max()))

            player_role = player_df["fanta_role"].dropna().iloc[0]
            mean_value = role_column_means.get(player_role, {}).get(col)
            if mean_value is not None:
                player_min_values.append(mean_value)
                player_max_values.append(mean_value)

        if player_min_values and player_max_values:
            y_min = min(player_min_values)
            y_max = max(player_max_values)

            # Avoid an empty axis range when every value is the same.
            if y_min == y_max:
                padding = max(abs(y_min) * 0.05, 0.01)
                y_min -= padding
                y_max += padding

            y_limits_dict[col] = (y_min, y_max)

    col1, _, col2 = st.columns([9,1,9])
    player_columns = [col1, col2]

    for player_name, player_column in zip(player_names, player_columns):
        chart_df = filtered_players[filtered_players["player"] == player_name].copy()
        chart_df = chart_df.sort_values("season")

        for col in columns_to_plot:
            chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")

        with player_column:

            # Players header
            fanta_role = chart_df["fanta_role"].dropna().iloc[0]
            role_name = get_roles_dict()[fanta_role].capitalize()
            role_badge_color = get_color_per_role(role=fanta_role, color_version=False)
            latest_team = chart_df["team"].dropna().iloc[-1]
            with st.container(border=True):
                st.markdown(
                    f"### :material/person: {player_name}",
                    text_alignment="center",
                )
                st.markdown(
                    f":{role_badge_color}-badge[{role_name} ({fanta_role})]  \n:violet-badge[{latest_team}]",
                    text_alignment="center",
                )

            # Creation of the plots
            for col in columns_to_plot:
                data = chart_df[["season", "team", col]].dropna(subset=["season", col])
                data = data.rename(columns={col: "value"})
                data["team"] = data["team"].fillna("Unknown team")
                user_view_col = get_user_view_of_column(col)

                st.markdown(
                    f"<h4 style='text-align: center;'>{user_view_col}</h4>",
                    unsafe_allow_html=True
                )

                if data.empty:
                    st.info("No data available for this statistic.")
                    continue

                y_min, y_max = y_limits_dict[col]
                mean_value = role_column_means.get(fanta_role, {}).get(col)
                chart = create_player_history_chart(
                    data,
                    user_view_col,
                    (y_min, y_max),
                    mean_value,
                )

                st.altair_chart(
                    chart,
                    width="stretch",
                )
    return


def plot_player_history(
        history_players: pd.DataFrame,
        player: str,
        columns_to_plot=None,
        feature=None,
        seasons_to_plot=None,
        disable_player_name=False,
        enable_ai_predictions=True,
        models_packages_dict=None,
    ) -> None:
    """
    Display the selected historical statistics for a single player.

    Each chart represents the evolution of one statistic across the requested
    number of recent seasons.

    Parameters
    ----------
    history_players:
        DataFrame containing the historical records of the players.
    """
    role_column_means = compute_role_column_means(history_players)
    full_player_history = history_players[history_players["player"].eq(player)].copy()

    if full_player_history.empty:
        st.info(f"No history available for {player}.")
        return

    full_player_history = full_player_history.sort_values("season")
    player_history = full_player_history.copy()
    player_roles = player_history["fanta_role"].dropna()
    if player_roles.empty:
        st.info(f"No Fantacalcio role available for {player}.")
        return
    
    fanta_role = player_roles.iloc[-1]

    # A specific feature takes precedence over a list of columns.
    if isinstance(feature, str) and feature:
        requested_columns = [feature]
    elif columns_to_plot is not None:
        requested_columns = list(columns_to_plot)
    else:
        role_name = get_roles_dict()[fanta_role]
        requested_columns = st.session_state.get(f"settings_{fanta_role}_graphical_cols_key", [])

    selected_columns = list(dict.fromkeys(
        column
        for column in requested_columns
        if isinstance(column, str) and column and column in player_history.columns
    ))

    # Case of no fields selected
    if not selected_columns:
        st.info("Select at least one statistic for this role in the Settings page.")
        return

    # Convert selected statistics to numeric values.
    for col in selected_columns:
        player_history[col] = pd.to_numeric(player_history[col], errors="coerce")

    # Player header
    player_name = player_history["player"].dropna().iloc[0]
    role_name = get_roles_dict()[fanta_role].capitalize()
    role_badge_color = get_color_per_role(role=fanta_role, color_version=False)
    player_teams = player_history["team"].dropna()
    latest_team = player_teams.iloc[-1] if not player_teams.empty else "Unknown team"

    with st.container(border=True, key=f"dark-card-{player_name}{f'_{feature}' if feature is not None else ''}"):
        
        if not disable_player_name:
            with st.container(border=True):
                st.markdown(
                    f"### :material/person: {player_name}",
                    text_alignment="center",
                    anchors=False,
                )
                st.markdown(
                    f":{role_badge_color}-badge[{role_name} ({fanta_role})]  \n:violet-badge[{latest_team}]",
                    text_alignment="center",
                )

        # Create one graphic for every selected column.
        for column in selected_columns:
            data = player_history[["season", "team", column]].dropna(subset=["season", column])
            data = data.rename(columns={column: "value"})
            data["team"] = data["team"].fillna("Unknown team")

            prediction_data = None
            can_predict_column = (
                enable_ai_predictions
                and column.endswith("_per90")
                and column in features_to_predict_per_role_dict.get(fanta_role, [])
                and models_packages_dict is not None
                and column in models_packages_dict
            )
            if can_predict_column:
                available_seasons = history_players["season"].dropna().astype(str).sort_values()
                if not available_seasons.empty:
                    current_season = available_seasons.iloc[-1]
                    prediction_history = full_player_history[
                        full_player_history["season"].astype(str).ne(current_season)
                    ]
                    model_package = models_packages_dict[column]
                    model_input = build_temporal_player_input(
                        player_history=prediction_history,
                        features=model_package["features"],
                    )
                    if model_input.attrs["available_lags"] > 0:
                        prediction = max(0.0, float(predict(
                            model_package=model_package,
                            player_history=model_input,
                        )))
                        prediction_data = pd.DataFrame({
                            "season": [current_season],
                            "value": [prediction],
                        })

            # Keep the requested number of historical seasons. For predicted
            # features, the current season is added separately as an extra point.
            if prediction_data is not None:
                data = data[data["season"].astype(str).ne(current_season)]
            if seasons_to_plot is not None:
                recent_seasons = (
                    data["season"]
                    .drop_duplicates()
                    .sort_values()
                    .tail(int(seasons_to_plot))
                )
                data = data[data["season"].isin(recent_seasons)].sort_values("season")

            st.markdown(
                f"#### {get_user_view_of_column(column)}",
                text_alignment="center",
                anchors=False,
            )
            if data.empty and prediction_data is None:
                st.info("No data available for this statistic.")
                continue

            mean_value = role_column_means.get(fanta_role, {}).get(column)
            chart = create_player_history_chart(
                data,
                statistic_name=get_user_view_of_column(column),
                mean_value=mean_value,
                prediction_data=prediction_data,
                enable_collapse_values=True
            )
            st.altair_chart(
                chart,
                width="stretch",
            )
    return


def has_full_team(fanta_manager: str) -> bool:
    """Return True when the Fanta Manager has filled every role."""
    fanta_manager_players_dict = st.session_state.get("fantacalcio_manager_players_dict_key", {})
    bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame())
    role_limit_keys_dict = {
        "P": "settings_P_limit_key",
        "D": "settings_D_limit_key",
        "C": "settings_C_limit_key",
        "A": "settings_A_limit_key",
    }

    if not isinstance(bought_players, pd.DataFrame) or "role" not in bought_players.columns:
        return False

    role_limits_dict = get_role_limits()
    role_counts = bought_players["role"].value_counts()
    for role, role_limit_key in role_limit_keys_dict.items():
        role_limit = st.session_state.get(role_limit_key, role_limits_dict[role])
        if role_counts.get(role, 0) != role_limit:
            return False

    return True


def save_bought_players(default_file_name: str = "fantacalcio_teams.pdf", format=".pdf"):
    """Generate the teams PDF and display its download controls in the sidebar."""
    fanta_manager_players_dict = st.session_state.get("fantacalcio_manager_players_dict_key", {})
    budget = st.session_state.get("settings_budget_key", 500)

    if not fanta_manager_players_dict:
        return

    try:
        pdf_buffer = BytesIO()
        must_have_columns = ["id", "player", "team", "role", "mantra_role", "mln"]
        column_names = ["ID", "Player", "Team", "Role", "Mantra Role", "Mln"]

        with PdfPages(pdf_buffer) as pdf:
            for fanta_manager, bought_players in fanta_manager_players_dict.items():
                players_df: pd.DataFrame = bought_players.copy()
                for column in must_have_columns:
                    if column not in players_df.columns:
                        players_df[column] = ""

                players_df["mln"] = pd.to_numeric(players_df["mln"], errors="coerce").fillna(0).astype(int)
                total_spent = int(players_df["mln"].sum())
                available_budget = int(budget - total_spent)

                role_order = {"P": 0, "D": 1, "C": 2, "A": 3}
                players_df["role_order"] = players_df["role"].map(role_order).fillna(4)
                players_df = players_df.sort_values(["role_order", "player"])[must_have_columns].fillna("")

                figure, axis = plt.subplots(figsize=(11.69, 8.27))
                axis.axis("off")
                axis.set_title(f"Fantacalcio team - {fanta_manager}", fontsize=18, fontweight="bold", pad=24)
                axis.text(0.02, 0.93, f"Total spent: {total_spent} mln", fontsize=11, transform=axis.transAxes)
                axis.text(0.98, 0.93, f"Available budget: {available_budget} mln", fontsize=11, ha="right", transform=axis.transAxes)
                
                table = axis.table(
                    cellText=players_df.astype(str).values,
                    colLabels=column_names,
                    colWidths=[0.08, 0.28, 0.20, 0.08, 0.18, 0.08],
                    cellLoc="center",
                    bbox=[0.02, 0.03, 0.96, 0.84],
                )
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                for (row, _), cell in table.get_celld().items():
                    if row == 0:
                        cell.set_facecolor("#4C78A8")
                        cell.set_text_props(color="white", fontweight="bold")
                    elif row % 2 == 0:
                        cell.set_facecolor("#EAF2F8")

                pdf.savefig(figure, bbox_inches="tight")
                plt.close(figure)

        pdf_data = pdf_buffer.getvalue()

        with st.sidebar:
            st.subheader("Auction PDF")
            st.caption("The completed teams are ready to download.")
            file_name = st.text_input(
                "File name",
                value=default_file_name,
                key="auction_pdf_file_name_key",
            ).strip()

            file_name = Path(file_name).name if file_name else default_file_name
            normalized_filename = "_".join(file_name.split('.')[0].split(" "))

            def baloons(df: pd.DataFrame):
                df.to_csv(f"../data/csv/pages/fantacalcio/{normalized_filename}.csv")
                st.balloons()
                st.session_state["show_auction_reset_confirmation_key"] = True

            st.download_button(
                label="Save as CSV",
                data=players_df.to_csv(),
                file_name=f"{normalized_filename}.csv",
                mime="application/csv",
                icon=":material/save:",
                type="primary",
                width="stretch",
                on_click=baloons,
                args=(players_df)
            )

            st.download_button(
                label="Save as PDF",
                data=pdf_data,
                file_name=f"{normalized_filename}.pdf",
                mime="application/pdf",
                icon=":material/save:",
                type="primary",
                width="stretch",
                on_click=baloons,
            )

        
        if st.session_state.get("show_auction_reset_confirmation_key", False):
            
            with st.sidebar:
                st.divider()

                st.info(
                    "To do another auction is needed the reset of the purchase players. Do you want to do it? "
                    "The downloaded PDF will not be deleted."
                )

                col1, col2 = st.columns(2)
                with col1:
                    reset_players = st.button(
                        "Reset",
                        icon=":material/restart_alt:",
                        type="primary",
                        width="stretch",
                        key="reset_auction_players_key",
                    )
                with col2:
                    keep_players = st.button(
                        "keep",
                        width="stretch",
                        key="keep_auction_players_key",
                    )

                if reset_players:
                    bought_player_columns = ["id", "player", "team", "role", "mantra_role", "manager", "mln"]
                    empty_bought_players = pd.DataFrame(columns=bought_player_columns)
                    fanta_managers = st.session_state.get("settings_managers_key", [])

                    st.session_state["fantacalcio_manager_players_dict_key"] = {
                        fanta_manager: empty_bought_players.copy()
                        for fanta_manager in fanta_managers
                    }
                    st.session_state["fantacalcio_bought_players_df_key"] = empty_bought_players

                    for key in list(st.session_state):
                        if str(key).startswith("fantacalcio_purchase_editor_"):
                            del st.session_state[key]

                    st.session_state.pop("show_auction_reset_confirmation_key", None)
                    st.rerun()

                if keep_players:
                    st.session_state.pop("show_auction_reset_confirmation_key", None)
                    st.rerun()

        return
    except Exception as e:
        st.error(f"Something went wrong saving the results of the auction:\n\n{e}\n")
        return
