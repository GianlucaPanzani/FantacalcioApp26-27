from pathlib import Path
from numbers import Integral, Real

import pandas as pd
import streamlit as st


role_limits_dict = {
    "P": st.session_state.get("fantacalcio_goalkeepers_limit_key", 3),
    "D": st.session_state.get("fantacalcio_defenders_limit_key", 8),
    "C": st.session_state.get("fantacalcio_midfielders_limit_key", 8),
    "A": st.session_state.get("fantacalcio_attackers_limit_key", 6),
}


def config_page(page_title="Football Dataset Explorer", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
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

def get_from_session_state(key: str):
    if key in st.session_state:
        return st.session_state[key]
    return None


def load_env(keys: list[str], path: str = ".env") -> dict:
    """Load selected values from an environment file into Session State."""
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

    loaded_values = {}
    for key in keys:
        # Keep values already initialized during the current session.
        if key in st.session_state or key not in env_values:
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
            csv_value = f"data/{default_name}.csv"
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


@st.cache_data(show_spinner=False)
def load_dataset(path: str, filter_by_current_year: bool = False, current_season: str = "2026-27") -> pd.DataFrame:
    """Load and cache a players dataset."""
    df = pd.read_csv(path, low_memory=False)
    return df.loc[df["season"].eq(current_season)].copy() if filter_by_current_year else df

def sync_filter(filter_key: str, widget_key: str) -> None:
    """Copy a widget value into its persistent filter state."""
    st.session_state[filter_key] = st.session_state.get(widget_key)

def plot_player_history(filtered_players: pd.DataFrame) -> None:
    """
    Display selectable historical statistics for a single player.

    Each chart represents the evolution of one statistic across seasons.
    Charts are arranged alternately in two columns.

    Parameters
    ----------
    filtered_players:
        DataFrame containing the historical records of one player.
    """

    chart_fields = {
        # General statistics
        "age": "Age",
        "appearances": "Appearances",
        "starts": "Starts",
        "minutes": "Minutes",
        "nineties": "90-minute periods",

        # Attacking statistics
        "goals_per90": "Goals per 90",
        "assists_per90": "Assists per 90",
        "goals_assists_per90": "Goals + assists per 90",
        "non_penalty_goals_per90": "Non-penalty goals per 90",
        "non_penalty_goals_assists_per90": "Non-penalty goals + assists per 90",
        "penalty_attempts_per90": "Penalty attempts per 90",
        "shots_on_target_pct": "Shots on target %",
        "shots_per90": "Shots per 90",
        "shots_on_target_per90": "Shots on target per 90",
        "goals_per_shot": "Goals per shot",
        "goals_per_shot_on_target": "Goals per shot on target",

        # Defensive statistics
        "interceptions_per90": "Interceptions per 90",
        "tackles_won_per90": "Tackles won per 90",
        "yellow_cards_per90": "Yellow cards per 90",
        "red_cards_per90": "Red cards per 90",

        # Goalkeeper statistics
        "goals_against_per90": "Goals against per 90",
        "shots_on_target_against_per90": "Shots on target against per 90",
        "saves_per90": "Saves per 90",
        "save_pct": "Save percentage",
        "wins_per90": "Wins per 90",
        "draws_per90": "Draws per 90",
        "losses_per90": "Losses per 90",
        "clean_sheets_per90": "Clean sheets per 90",
        "clean_sheet_pct": "Clean sheet percentage",
        "keeper_penalty_attempts_per90": "Penalties faced per 90",
        "penalties_allowed_per90": "Penalties allowed per 90",
        "penalties_saved_per90": "Penalties saved per 90",
        "penalties_missed_per90": "Penalties missed per 90",
    }

    # Remove fields not present in the current dataset.
    available_fields = {field: label for field, label in chart_fields.items() if field in filtered_players.columns}

    # Fields selection
    selected_fields = st.multiselect(
        label="Select statistics",
        options=list(available_fields),
        default=[
            field for field in [
                "appearances",
                "minutes",
                "goals_per90",
                "assists_per90",
            ] if field in available_fields
        ],
        format_func=lambda field: available_fields[field],
    )

    # Case of no fields selected
    if not selected_fields:
        st.info("Select at least one statistic.")
        return

    # Convert selected statistics to numeric values.
    chart_df = filtered_players.copy()
    chart_df = chart_df.sort_values("season")
    for field in selected_fields:
        chart_df[field] = pd.to_numeric(chart_df[field], errors="coerce")

    # Create the graphics in selected_fields in 2 columns
    col1, col2 = st.columns(2)
    for index, field in enumerate(selected_fields):
        container = col1 if index % 2 == 0 else col2
        data = chart_df[["season", field]].dropna()

        with container:
            st.markdown(
                f"<h4 style='text-align: center;'>{available_fields[field]}</h4>",
                unsafe_allow_html=True
            )

            st.line_chart(
                data,
                x="season",
                y=field,
                x_label="Season",
                y_label=available_fields[field],
                use_container_width=True,
            )
