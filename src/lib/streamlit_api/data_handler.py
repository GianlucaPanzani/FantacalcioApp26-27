from io import BytesIO
import json
import joblib
from numbers import Integral, Real
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import pandas as pd
from pandas.api.types import (
    is_bool_dtype,
    is_datetime64_any_dtype,
    is_float_dtype,
    is_integer_dtype,
    is_string_dtype,
)
import streamlit as st
from backend import db_api
from backend.persistent_state_db import (
    get_persistent_state,
    get_persistent_states,
    set_persistent_state,
    update_persistent_state,
)
from lib.data_handler import store_guest_archive
from lib.utils import (
    stats_persistent_key_fields,
    get_current_date,
    get_current_season,
)


def set_format_interest(interest):
    """Convert a non-null interest value to display text."""
    if interest is None:
        return None
    return str(interest)


def get_condition_by(
    df: pd.DataFrame, column: str, selected_values, compare_op: str,
):
    """Build the pandas condition for one configured dataset filter."""
    if isinstance(selected_values, (list, tuple, set)):
        return df[column].isin(selected_values)
    if compare_op == "eq":
        return df[column] == selected_values
    if compare_op == "geq":
        return df[column] >= selected_values
    if compare_op == "leq":
        return df[column] <= selected_values
    return df[column] == selected_values


def get_default_value(column: pd.Series):
    """Return an empty filter value compatible with a pandas Series dtype."""
    if is_bool_dtype(column):
        return False
    if is_integer_dtype(column):
        return 0
    if is_float_dtype(column):
        return 0.0
    if is_datetime64_any_dtype(column):
        return pd.NaT
    if is_string_dtype(column):
        return ""

    values = column.dropna()
    if not values.empty:
        sample_value = values.iloc[0]
        if isinstance(sample_value, list):
            return []
        if isinstance(sample_value, dict):
            return {}
        if isinstance(sample_value, tuple):
            return ()

    return None



@st.cache_data(show_spinner=False)
def load_dataset(path: str, filter_by_current_year: bool = False, current_season: str = "2026-27") -> pd.DataFrame:
    """Load and cache a CSV dataset, optionally keeping one season.

    Params
    ----------
    path : str
        Path to the CSV file.
    filter_by_current_year : bool
        Whether to keep only rows for ``current_season``.
    current_season : str
        Season label used by the optional filter.

    Returns
    -------
    pandas.DataFrame
        Loaded dataset or its current-season subset.
    """
    df = pd.read_csv(path, low_memory=False)
    return df.loc[df["season"].eq(current_season)].copy() if filter_by_current_year else df


@st.cache_resource
def load_models(target_features: list) -> dict:
    """Load and cache one serialized model package per target feature.

    Params
    ----------
    target_features : list
        Target names used in the ``models/xgb_<target>.pkl`` filenames.

    Returns
    -------
    dict
        Model packages indexed by target feature.
    """
    models_packages_dict = {}
    for feature in target_features:
        models_packages_dict[feature] = joblib.load(f"models/xgb_{feature}.pkl")
    return models_packages_dict


def apply_filters(
    df: pd.DataFrame,
    exclude=None,
    columns_to_filter_list=[],
    compare_op_for_columns_to_filter_dict={},
    page="unknown_page",
    filter_keys: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Apply the page filters stored in Streamlit Session State.

    Params
    ----------
    df : pandas.DataFrame
        Dataset to filter.
    exclude : str or None
        Column whose active filter should be ignored.
    columns_to_filter_list : list
        Columns with filter values stored in Session State.
    compare_op_for_columns_to_filter_dict : dict
        Comparison operator configured for each filter column.
    page : str
        Page prefix used to build Session State keys.
    filter_keys : dict or None
        Optional Session State key to use for each filtered column.

    Returns
    -------
    pandas.DataFrame
        Filtered copy of the input dataset.
    """
    result = df.copy()

    filter_keys = filter_keys or {}
    for column in columns_to_filter_list:
        filter_key = filter_keys.get(column, f"{page}_{column}_key")
        selected_values = st.session_state.get(
            filter_key,
            get_default_value(result[column]),
        )
        if exclude == column or not selected_values:
            continue
        result = result[
            get_condition_by(result, column, selected_values, compare_op_for_columns_to_filter_dict[column])
        ]

    return result


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


def get_role_limits() -> dict:
    """Return configured squad limits indexed by Fantacalcio role."""
    return {
        "P": st.session_state.get("settings_P_limit_widget_key", 3),
        "D": st.session_state.get("settings_D_limit_widget_key", 8),
        "C": st.session_state.get("settings_C_limit_widget_key", 8),
        "A": st.session_state.get("settings_A_limit_widget_key", 6),
    }


def get_roles_list(enable_aka=False) -> list:
    """Return readable role names, optionally including role codes."""
    return [
        "goalkeeper" + f"{' (P)' if enable_aka else ''}",
        "defender" + f"{' (D)' if enable_aka else ''}",
        "midfielder" + f"{' (C)' if enable_aka else ''}", 
        "attacker" + f"{' (A)' if enable_aka else ''}"
    ]


def get_roles_dict() -> dict:
    """Return readable role names indexed by Fantacalcio role code."""
    return {
        "P": "goalkeeper",
        "D": "defender",
        "C": "midfielder",
        "A": "attacker"
    }


def get_role_budget_limits() -> dict:
    """Return configured spending targets indexed by Fantacalcio role."""
    return {
        "P": st.session_state.get("settings_P_budget_limit_widget_key", 50),
        "D": st.session_state.get("settings_D_budget_limit_widget_key", 100),
        "C": st.session_state.get("settings_C_budget_limit_widget_key", 200),
        "A": st.session_state.get("settings_A_budget_limit_widget_key", 150),
    }


def get_auction_data():
    return {
    "name": f"Auction {get_current_season()}",
    "season": get_current_season(),
    "auction_code_hash": None,
    "player_extraction_order": None,
    "status": "lobby", # running, completed
    "total_budget": int(st.session_state.get("settings_budget_widget_key", 500)),
    "goalkeeper_slots": int(st.session_state.get("settings_P_limit_widget_key", 3)),
    "defender_slots": int(st.session_state.get("settings_D_limit_widget_key", 8)),
    "midfielder_slots": int(st.session_state.get("settings_C_limit_widget_key", 8)),
    "forward_slots": int(st.session_state.get("settings_A_limit_widget_key", 6)),
    "defender_modifier_enabled": int(bool(st.session_state.get("settings_auction_defender_modifier_widget_key", False))),
    "midfielder_modifier_enabled": int(bool(st.session_state.get("settings_auction_midfielder_modifier_widget_key", False))),
    "player_switch_enabled": int(bool(st.session_state.get("settings_auction_player_switch_widget_key", False))),
    "player_extraction_scope": st.session_state.get("settings_player_extraction_type_widget_key", "on_all_players"),
    "role_extraction_order": st.session_state.get("settings_role_extraction_order_widget_key", "in_order_P_D_C_A"),
    "points_goal_scored": float(st.session_state.get("settings_points_goal_scored_widget_key", 3)),
    "points_goalkeeper_goal_conceded": float(st.session_state.get("settings_points_goalkeeper_goal_conceded_widget_key", -1)),
    "points_assist": float(st.session_state.get("settings_points_assist_widget_key", 1)),
    "points_penalty_scored": float(st.session_state.get("settings_points_penalty_scored_widget_key", 3)),
    "points_penalty_missed": float(st.session_state.get("settings_points_penalty_missed_widget_key", -3)),
    "points_goalkeeper_penalty_conceded": float(st.session_state.get("settings_points_goalkeeper_penalty_conceded_widget_key", -1)),
    "points_goalkeeper_penalty_saved": float(st.session_state.get("settings_points_goalkeeper_penalty_saved_widget_key", 3)),
    "points_yellow_card": float(st.session_state.get("settings_points_yellow_card_widget_key", -0.5)),
    "points_red_card": float(st.session_state.get("settings_points_red_card_widget_key", -1)),
}


def get_fanta_manager_players_dict() -> dict:
    """Return purchased players grouped by Fanta Manager.

    Rebuild the mapping from the restored CSV DataFrame when Session State does
    not contain it yet, while preserving managers with no purchases.

    Returns
    -------
    dict
        Fanta Manager names mapped to their purchased-player DataFrames.
    """
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
    """Return a Session State value, or ``None`` when its key is absent."""
    if key in st.session_state:
        return st.session_state[key]
    return None


def _serialize_persistent_value(value) -> str:
    """Serialize one supported Session State value as valid JSON."""
    if isinstance(value, pd.DataFrame):
        value = {
            "__persistent_type__": "pandas.DataFrame",
            "value": value.to_json(orient="split"),
        }
    elif isinstance(value, tuple):
        value = {"__persistent_type__": "tuple", "value": list(value)}
    elif isinstance(value, Integral) and not isinstance(value, bool):
        value = int(value)
    elif isinstance(value, Real) and not isinstance(value, bool):
        value = float(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def _deserialize_persistent_value(value_json: str):
    """Decode one JSON value, restoring supported structured Python types."""
    value = json.loads(value_json)
    if isinstance(value, dict) and value.get("__persistent_type__") == "pandas.DataFrame":
        return pd.read_json(BytesIO(value["value"].encode("utf-8")), orient="split")
    if isinstance(value, dict) and value.get("__persistent_type__") == "tuple":
        return tuple(value["value"])
    return value


def load_persistent_state(
    user_id: int,
    page_names: list[str] | None = None,
) -> dict:
    """Load persisted user values into Session State without overwriting it.

    Params
    ----------
    user_id : int
        Identifier of the authenticated user.
    page_names : list of str or None
        Pages to load, or ``None`` to load every persisted page.

    Returns
    -------
    dict
        Loaded values, including values already initialized in this session.
    """
    rows = get_persistent_states({"user_id": user_id})
    if page_names is not None:
        allowed_pages = set(page_names)
        rows = [row for row in rows if row["page_name"] in allowed_pages]

    scope = "all" if page_names is None else ",".join(sorted(page_names))
    loaded_marker = f"_persistent_state_loaded_{user_id}_{scope}"
    first_load = not st.session_state.get(loaded_marker, False)
    loaded_values = {}
    for row in rows:
        key = row["key"]
        if first_load or key not in st.session_state:
            st.session_state[key] = _deserialize_persistent_value(row["value_json"])
        loaded_values[key] = st.session_state[key]
    st.session_state[loaded_marker] = True
    return loaded_values


def store_persistent_state(user_id: int, data_dict: dict) -> dict:
    """Persist changed Session State values for one user in one transaction.

    Params
    ----------
    user_id : int
        Identifier of the authenticated user.
    data_dict : dict
        Persistent keys mapped to their current values.

    Returns
    -------
    dict
        Values successfully serialized and stored.
    """
    stored_values = {}
    with db_api.transaction() as connection:
        existing_rows = get_persistent_states(
            {"user_id": user_id},
            connection=connection,
        )
        existing_values = {
            (row["page_name"], row["key"]): row["value_json"]
            for row in existing_rows
        }
        for key, value in data_dict.items():
            if not isinstance(key, str) or "_" not in key:
                continue
            page_name = key.split("_", 1)[0]
            value_json = _serialize_persistent_value(value)
            existing_value = existing_values.get((page_name, key))
            if existing_value is None:
                set_persistent_state(
                    {
                        "user_id": user_id,
                        "page_name": page_name,
                        "key": key,
                        "value_json": value_json,
                    },
                    connection=connection,
                )
            elif existing_value != value_json:
                update_persistent_state(
                    user_id,
                    page_name,
                    key,
                    {"value_json": value_json},
                    connection=connection,
                )
            stored_values[key] = value
    return stored_values


def load_config(keys: list[str] | None = None, path: str = ".env") -> dict:
    """Load selected typed configuration values into Session State.

    Params
    ----------
    keys : list of str or None
        Values to load; every non-type key when omitted.
    path : str
        Environment file to read.

    Returns
    -------
    dict
        Values loaded or already present in Session State.
    """
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


def store_config(data_dict: dict, path: str = ".env") -> dict:
    """Persist non-user configuration in the application's typed env format.

    Params
    ----------
    data_dict : dict
        Session values to persist.
    path : str
        Environment file to update.

    Returns
    -------
    dict
        Values successfully serialized to the file.
    """
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
            page_name = default_name.split("_")[0]
            csv_value = f"data/csv/pages/{page_name}/{default_name}_{get_current_date()}_{get_current_season()}.csv"
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


def restore_personal_backup(
    upload_key: str,
    result_key: str,
    user_id: int,
    username: str,
) -> None:
    """Restore a personal backup and clear stale Session State values.

    Params
    ----------
    upload_key : str
        Session State key containing the uploaded ZIP file.
    result_key : str
        Session State key that receives a success or error message.
    user_id : int
        Identifier of the user whose persistent state is replaced.
    username : str
        Username used for the restored selected-player CSV filename.
    """
    uploaded_archive = st.session_state.get(upload_key)

    try:
        result = store_guest_archive(
            uploaded_archive.getvalue(),
            user_id,
            username,
        )
    except (ValueError, OSError) as error:
        st.session_state[result_key] = {
            "success": False,
            "message": str(error),
        }
        return

    restored_keys = set(result["settings"])
    restored_widget_keys = {
        f"{key.removesuffix('_key')}_widget_key"
        for key in restored_keys
        if key.endswith("_key") and not key.endswith("_widget_key")
    }

    # Allow load_persistent_state() to reload restored values on the next rerun.
    for key in list(st.session_state):
        if (
            key.startswith("selection_")
            or key in restored_keys
            or key in restored_widget_keys
        ):
            del st.session_state[key]

    st.session_state[result_key] = {
        "success": True,
        "message": (
            f"Backup restored successfully. "
            f"{result['selected_players']} selected players imported."
        ),
    }


def restore_bought_players(bought_players_df_key: str, settings_managers_key: str, fanta_manager_players_dict_key:str):
    """Rebuild purchased-player groups from a restored CSV DataFrame.

    Params
    ----------
    bought_players_df_key : str
        Session State key containing the restored purchases DataFrame.
    settings_managers_key : str
        Session State key containing every configured Fanta Manager.
    fanta_manager_players_dict_key : str
        Session State key that receives the rebuilt manager mapping.
    """
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
    """Copy selected chart columns from a widget into persistent state."""
    st.session_state[graphical_cols_key].extend(st.session_state[widget_key])
    st.session_state[widget_key] = []


def has_full_team(fanta_manager: str, page_name: str = "fantacalcio") -> bool:
    """Return True when the Fanta Manager has filled every role."""
    fanta_manager_players_dict = st.session_state.get(f"{page_name}_manager_players_dict_key", {})
    bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame())
    role_limit_keys_dict = {
        "P": "settings_P_limit_widget_key",
        "D": "settings_D_limit_widget_key",
        "C": "settings_C_limit_widget_key",
        "A": "settings_A_limit_widget_key",
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


def save_bought_players(page_name: str):
    """Generate the teams PDF and display its download controls in the sidebar."""
    fanta_manager_players_dict = st.session_state.get(f"{page_name}_manager_players_dict_key", {})
    budget = st.session_state.get("settings_budget_widget_key", 500)

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

        with st.container(border=True, key=f"dark-card-{page_name}_download_key"):
            file_name = st.text_input(
                "File name",
                value=f"{page_name}_{get_current_season()}",
                key="auction_file_name_key",
            ).strip()
            file_name = Path(file_name).name
            normalized_filename = file_name.split('.')[0].split(" ")
            
            def baloons():
                """Show the completion balloons for a finished squad."""
                st.balloons()
                st.session_state["show_auction_reset_confirmation_key"] = True

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="Save as CSV",
                    data=players_df.to_csv(),
                    file_name=f"{normalized_filename}.csv",
                    mime="application/csv",
                    icon=":material/save:",
                    type="primary",
                    width="stretch",
                    on_click=baloons,
                )
            with col2:
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

        return
    except Exception as e:
        st.error(f"Something went wrong saving the results of the auction:\n\n{e}\n")
        return
