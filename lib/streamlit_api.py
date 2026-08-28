from io import BytesIO
import time
from numbers import Integral, Real
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
import streamlit as st

# Session state keys of which value has to persist between sessions
persistent_session_keys = [
    "my_fanta_manager_key",
    "fanta_managers_key",
    "fantacalcio_budget_key",
    "fantacalcio_goalkeepers_budget_limit_key",
    "fantacalcio_defenders_budget_limit_key",
    "fantacalcio_midfielders_budget_limit_key",
    "fantacalcio_attackers_budget_limit_key",
    "fantacalcio_goalkeepers_limit_key",
    "fantacalcio_defenders_limit_key",
    "fantacalcio_midfielders_limit_key",
    "fantacalcio_attackers_limit_key",
    "ai_enabled_key",
    "bought_players_df_key",
]

def config_page(page_title="Fantacalcio tool", page_icon="⚽", layout="wide", initial_sidebar_state="expanded"):
    st.set_page_config(
        page_title=page_title,
        page_icon=page_icon,
        layout=layout,
        initial_sidebar_state=initial_sidebar_state,
    )

def highlight_bought_rows(row, fanta_managers):
    '''Highlight players bought by the user or by another fanta manager'''
    if row["bought"] == st.session_state["my_fanta_manager_key"]:
        row_style = "background-color: rgba(40, 167, 69, 0.25)"
    elif row["bought"] in fanta_managers:
        row_style = "background-color: rgba(220, 53, 69, 0.25)"
    else:
        row_style = ""
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

def get_role_limits() -> dict:
    return {
        "P": st.session_state.get("fantacalcio_goalkeepers_limit_key", 3),
        "D": st.session_state.get("fantacalcio_defenders_limit_key", 8),
        "C": st.session_state.get("fantacalcio_midfielders_limit_key", 8),
        "A": st.session_state.get("fantacalcio_attackers_limit_key", 6),
    }


def get_role_budget_limits() -> dict:
    return {
        "P": st.session_state.get("fantacalcio_goalkeepers_budget_limit_key", 50),
        "D": st.session_state.get("fantacalcio_defenders_budget_limit_key", 100),
        "C": st.session_state.get("fantacalcio_midfielders_budget_limit_key", 200),
        "A": st.session_state.get("fantacalcio_attackers_budget_limit_key", 150),
    }

def get_fanta_manager_players_dict() -> dict:
    # Case of rebuild of the bought players dict by restoring from csv
    if "fanta_manager_players_dict_key" not in st.session_state:
        fanta_manager_players_dict = {}

        # Restore data from csv
        restored_players = st.session_state.get("bought_players_df_key", pd.DataFrame())

        # Rebuilt of the bought players dict
        if not restored_players.empty and "manager" in restored_players.columns:
            for fanta_manager, bought_players in restored_players.groupby("manager"):
                fanta_manager_players_dict[fanta_manager] = bought_players.reset_index(drop=True)

        # Preserve Fanta Managers without bought players
        if "fanta_managers_key" in st.session_state:
            fanta_managers = st.session_state["fanta_managers_key"]
            for fanta_manager in fanta_managers:
                fanta_manager_players_dict.setdefault(fanta_manager, pd.DataFrame())

        st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

    # Case of data already present in session_state
    fanta_manager_players_dict = st.session_state["fanta_manager_players_dict_key"]
    return fanta_manager_players_dict

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


def has_full_team(fanta_manager: str) -> bool:
    """Return True when the Fanta Manager has filled every role."""
    fanta_manager_players_dict = st.session_state.get("fanta_manager_players_dict_key", {})
    bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame())
    role_limit_keys_dict = {
        "P": "fantacalcio_goalkeepers_limit_key",
        "D": "fantacalcio_defenders_limit_key",
        "C": "fantacalcio_midfielders_limit_key",
        "A": "fantacalcio_attackers_limit_key",
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


def generate_pdf_with_bought_players(default_file_name: str = "fantacalcio_teams.pdf"):
    """Generate the teams PDF and display its download controls in the sidebar."""
    fanta_manager_players_dict = st.session_state.get("fanta_manager_players_dict_key", {})
    budget = st.session_state.get("fantacalcio_budget_key", 500)

    if not fanta_manager_players_dict:
        return

    try:
        pdf_buffer = BytesIO()
        must_have_columns = ["id", "player", "team", "role", "mantra_role", "mln"]
        column_names = ["ID", "Player", "Team", "Role", "Mantra Role", "Mln"]

        with PdfPages(pdf_buffer) as pdf:
            for fanta_manager, bought_players in fanta_manager_players_dict.items():
                players_df = bought_players.copy()
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

        st.sidebar.subheader("Auction PDF")
        st.sidebar.caption("The completed teams are ready to download.")
        file_name = st.sidebar.text_input(
            "File name",
            value=default_file_name,
            key="auction_pdf_file_name_key",
        ).strip()

        file_name = Path(file_name).name if file_name else default_file_name
        if not file_name.lower().endswith(".pdf"):
            file_name = f"{file_name}.pdf"

        def balloons():
            st.balloons()
            st.session_state["show_auction_reset_confirmation_key"] = True

        st.sidebar.download_button(
            label="Save PDF",
            data=pdf_data,
            file_name=file_name,
            mime="application/pdf",
            icon=":material/save:",
            type="primary",
            width="stretch",
            on_click=balloons,
        )

        
        if st.session_state.get("show_auction_reset_confirmation_key", False):
            
            with st.sidebar:
                st.divider()

                st.warning(
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
                    fanta_managers = st.session_state.get("fanta_managers_key", [])

                    st.session_state["fanta_manager_players_dict_key"] = {
                        fanta_manager: empty_bought_players.copy()
                        for fanta_manager in fanta_managers
                    }
                    st.session_state["bought_players_df_key"] = empty_bought_players

                    for key in list(st.session_state):
                        if str(key).startswith("purchase_editor_"):
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
