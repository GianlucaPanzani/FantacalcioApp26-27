from datetime import datetime
from pathlib import Path
import time
import pandas as pd
import numpy as np
from base64 import b64encode
from rapidfuzz import fuzz
import re
import unicodedata
from pandas.api.types import (
    is_bool_dtype,
    is_integer_dtype,
    is_float_dtype,
    is_string_dtype,
    is_datetime64_any_dtype,
)


stats_persistent_key_fields = [
    "selected",
    "mln",
    "interest",
    "description",
]

columns_to_user_view_dict = {
    "selected": "Select",
    "mln": "💰 Mln",
    "interest": "Interest",
    "description": "Description",
    "Id": "Fanta ID",
    "R": "Fanta role",
    "RM": "Mantra role",
    "Nome": "Player",
    "id": "ID",
    "season": "Season",
    "player": "Player",
    "team": "Old team",
    "competition": "Competition",
    "nationality": "Nationality",
    "position": "Role",
    "fanta_role": "Fanta role",
    "mantra_role": "Mantra role",
    "age": "Age",
    "birth_year": "Birth year",
    "appearances": "Appearances",
    "starts": "Starts",
    "minutes": "Minutes played",
    "nineties": "90-minutes played",
    "goals_per90": "Goals per 90",
    "assists_per90": "Assists per 90",
    "goals_assists_per90": "Goals + assists per 90",
    "non_penalty_goals_per90": "Non-penalty goals per 90",
    "non_penalty_goals_assists_per90": "Non-penalty goals + assists per 90",
    "penalty_attempts_per90": "Penalty attempts per 90",
    "yellow_cards_per90": "Yellow cards per 90",
    "red_cards_per90": "Red cards per 90",
    "shots_on_target_pct": "Shots on target prc",
    "shots_per90": "Shots per 90",
    "shots_on_target_per90": "Shots on target per 90",
    "goals_per_shot": "Goals per shot",
    "goals_per_shot_on_target": "Goals per shot on target",
    "interceptions_per90": "Interceptions per 90",
    "tackles_won_per90": "Tackles won per 90",
    "goals_against_per90": "Goals conceded per 90",
    "shots_on_target_against_per90": "Shots on target against per 90",
    "saves_per90": "Saves per 90",
    "save_pct": "Save pct",
    "wins_per90": "Wins per 90",
    "draws_per90": "Draws per 90",
    "losses_per90": "Losses per 90",
    "clean_sheets_per90": "Clean sheets per 90",
    "clean_sheet_pct": "Clean sheet pct",
    "keeper_penalty_attempts_per90": "Penalties faced per 90",
    "penalties_allowed_per90": "Penalties conceded per 90",
    "penalties_saved_per90": "Penalties saved per 90",
    "penalties_missed_per90": "Penalties missed per 90",
    "normalized_name": "Normalized name",
    "Squadra": "Team",
    "Qt.A": "Quote",
    "Qt.I": "Initial quote",
    "Diff.": "Quote diff.",
    "Qt.A M": "Mantra quote",
    "Qt.I M": "Initial Mantra quote",
    "Diff.M": "Mantra quote diff.",
    "FVM": "Mean Fanta mln",
    "FVM M": "Mean Mantra mln",
}

interest_markers = {
    "Da valutare": "⚫",
    "Bassissimo": "⚪",
    "Basso": "🟡",
    "Medio": "🟠",
    "Alto": "🔴",
    "Scommessa": "🟣",
    "Buoni low cost": "🔵",
}

def get_ai_icon():
    return f"![AI](data:image/png;base64,{b64encode(Path('icons/icons_ai.png').read_bytes()).decode('ascii')})"

def get_role_icon(fanta_role: str):
    role_icons = {
        "P": "🧤",
        "D": "🛡️",
        "C": "⚽",
        "A": "🎯"
    }
    return role_icons[fanta_role]


def get_ai_player_selection_icon():
    return f"![AI](data:image/png;base64,{b64encode(Path('icons/icons_ai_chatgpt_players_selection2.png').read_bytes()).decode('ascii')})"

def set_format_interest(interest):
    if interest is None:
        return None
    return interest_markers.get(interest, interest)

def get_current_year():
    return datetime.now().year

def ai_data_stream(text: str):
    words = text.split(" ")
    n_words = len(words)
    for i, word in enumerate(words):
        time.sleep(0.01)
        next_word = word + " " if i < n_words - 1 else word
        yield next_word
    return

def highlight_player_role(row: pd.Series) -> list[str]:
    """Apply the Fantacalcio role color to every read-only player cell."""
    role_color = get_color_per_role(row.get("R", row.get("fanta_role", "")))
    if not role_color:
        return [""] * len(row)
    return [f"background-color: {role_color}; color: #212121"] * len(row)

def get_color_per_role(role: str, color_version=True, rgba=False) -> str:
    """Return a soft Material Design color for a Fantacalcio role."""
    role_colors_dict = {
        "P": "#EACD6D" if color_version else "orange",  # Previous: "#FFD54F"
        "D": "#8FCD92"  if color_version else "green",  # Previous: "#81C784"
        "C": "#73B3E7" if color_version else "blue",  # Previous: "#64B5F6"
        "A": "#DE7D7D" if color_version else "red",  # Previous: "#E57373"
    }
    role_colors_rgba_dict = {
        "P": "rgba(240,165,0,0.80)",
        "D": "rgba(88,185,92,0.80)",
        "C": "rgba(33,150,243,0.80)",
        "A": "rgba(230,70,60,0.80)",
    }
    if rgba:
        return role_colors_rgba_dict.get(role, "")
    return role_colors_dict.get(str(role).strip().upper(), "")
    

def get_circular_role_icon(role: str, font_size=14, height=24, width=24, y_translation=-2):
    return f"""
    <span style="
        width: {width}px;
        height: {height}px;
        border-radius: 50%;
        background-color: {get_color_per_role(role, color_version=False)};
        display: inline-flex;
        align-items: center;
        justify-content: center;
        vertical-align: middle;
        transform: translateY({y_translation}px);
        line-height: 1;
        margin: 0;
        font-weight: bold;
        color: white;
        font-size: {font_size}px;
    ">{role}</span>
    """

def get_teams_dict():
    return {
        'Atalanta':   {'rate': 75, 'goals_done': 55, 'goals_against': 39, 'n_matches': 41, 'goals_done_per90': 1.34, 'goals_against_per90': 0.95},
        'Bologna':    {'rate': 55, 'goals_done': 51, 'goals_against': 50, 'n_matches': 41, 'goals_done_per90': 1.24, 'goals_against_per90': 1.22},
        'Cagliari':   {'rate': 45, 'goals_done': 42, 'goals_against': 54, 'n_matches': 41, 'goals_done_per90': 1.02, 'goals_against_per90': 1.32},
        'Como':       {'rate': 85, 'goals_done': 72, 'goals_against': 32, 'n_matches': 41, 'goals_done_per90': 1.76, 'goals_against_per90': 0.78},
        'Fiorentina': {'rate': 55, 'goals_done': 42, 'goals_against': 59, 'n_matches': 41, 'goals_done_per90': 1.02, 'goals_against_per90': 1.44},
        'Frosinone':  {'rate': 65, 'goals_done': 6,  'goals_against': 3,  'n_matches': 3,  'goals_done_per90': 2.00, 'goals_against_per90': 1.00},
        'Genoa':      {'rate': 30, 'goals_done': 42, 'goals_against': 58, 'n_matches': 41, 'goals_done_per90': 1.02, 'goals_against_per90': 1.41},
        'Juventus':   {'rate': 85, 'goals_done': 65, 'goals_against': 35, 'n_matches': 41, 'goals_done_per90': 1.59, 'goals_against_per90': 0.85},
        'Inter':      {'rate': 100, 'goals_done': 97, 'goals_against': 38, 'n_matches': 41, 'goals_done_per90': 2.37, 'goals_against_per90': 0.93},
        'Lazio':      {'rate': 65, 'goals_done': 45, 'goals_against': 41, 'n_matches': 41, 'goals_done_per90': 1.10, 'goals_against_per90': 1.00},
        'Lecce':      {'rate': 45, 'goals_done': 30, 'goals_against': 55, 'n_matches': 41, 'goals_done_per90': 0.73, 'goals_against_per90': 1.34},
        'Milan':      {'rate': 85, 'goals_done': 58, 'goals_against': 37, 'n_matches': 41, 'goals_done_per90': 1.41, 'goals_against_per90': 0.90},
        'Monza':      {'rate': 35, 'goals_done': 4,  'goals_against': 8,  'n_matches': 3,  'goals_done_per90': 1.33, 'goals_against_per90': 2.67},
        'Napoli':     {'rate': 80, 'goals_done': 63, 'goals_against': 41, 'n_matches': 41, 'goals_done_per90': 1.54, 'goals_against_per90': 1.00},
        'Parma':      {'rate': 45, 'goals_done': 29, 'goals_against': 50, 'n_matches': 41, 'goals_done_per90': 0.71, 'goals_against_per90': 1.22},
        'Roma':       {'rate': 90, 'goals_done': 69, 'goals_against': 32, 'n_matches': 41, 'goals_done_per90': 1.68, 'goals_against_per90': 0.78},
        'Sassuolo':   {'rate': 55, 'goals_done': 51, 'goals_against': 55, 'n_matches': 41, 'goals_done_per90': 1.24, 'goals_against_per90': 1.34},
        'Torino':     {'rate': 45, 'goals_done': 48, 'goals_against': 68, 'n_matches': 41, 'goals_done_per90': 1.17, 'goals_against_per90': 1.66},
        'Udinese':    {'rate': 50, 'goals_done': 50, 'goals_against': 53, 'n_matches': 41, 'goals_done_per90': 1.22, 'goals_against_per90': 1.29},
        'Venezia':    {'rate': 25, 'goals_done': 2,  'goals_against': 7,  'n_matches': 3, 'goals_done_per90': 0.67, 'goals_against_per90': 2.33},
    }

def normalize_name(name: str) -> str:
    """Normalize a player name for fuzzy comparison."""
    name = unicodedata.normalize("NFD", str(name))
    name = "".join(char for char in name if unicodedata.category(char) != "Mn")
    name = re.sub(r"[^\w\s.]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()

def get_condition_by(df: pd.DataFrame, column: str, selected_values, compare_op: str):
    """Return the appropriate filtering condition."""
    if isinstance(selected_values, (list, tuple, set)):
        return df[column].isin(selected_values)
    if compare_op == "eq":
        return df[column] == selected_values
    elif compare_op == "geq":
        return df[column] >= selected_values
    elif compare_op == "leq":
        return df[column] <= selected_values
    return df[column] == selected_values

def get_default_value(column: pd.Series):
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

    # Object columns may contain lists, dictionaries or other Python objects.
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

def generate_name_variants(full_name: str) -> list[str]:
    """
    Generate common full-name and abbreviated-name representations.

    Examples
    --------
    "Lautaro Martinez" ->
    ["Lautaro Martinez", "L. Martinez", "Lautaro M.", "Martinez"]

    "David de Gea" ->
    ["David de Gea", "D. de Gea", "David G.", "de Gea"]
    """
    full_name = str(full_name).strip()
    parts = full_name.split()

    if not full_name:
        return []

    if len(parts) == 1:
        return [full_name]

    first_name = parts[0]
    surname = " ".join(parts[1:])
    last_surname = parts[-1]

    variants = [
        full_name,
        surname,
        f"{first_name[0]}. {surname}",
        f"{first_name} {last_surname[0]}.",
    ]

    # Also support names written as "Surname N."
    if len(parts[-1].replace(".", "")) == 1:
        initial = parts[-1].replace(".", "")
        surname_first = " ".join(parts[:-1])

        variants.extend([
            f"{initial}. {surname_first}",
            surname_first,
        ])

    # Remove duplicates while preserving order.
    return list(dict.fromkeys(variants))


def get_candidates_by_season(
    fanta_name: str,
    history_df: pd.DataFrame,
    top_k: int = 3,
    season_column: str = "season",
    name_column: str = "player",
) -> pd.DataFrame:
    """
    Select the best historical candidates for each season.

    Each historical name is compared through multiple common abbreviations.
    The best score among its variants becomes the candidate name score.
    """
    fanta_variants = generate_name_variants(fanta_name)

    if not fanta_variants:
        fanta_variants = [fanta_name]

    normalized_fanta_variants = [
        normalize_name(name)
        for name in fanta_variants
    ]

    candidates = []
    for _, season_df in history_df.groupby(season_column, sort=False):
        season_candidates = []
        for _, history_row in season_df.iterrows():
            historical_name = str(history_row.get(name_column, ""))
            historical_variants = generate_name_variants(historical_name)

            best_score = -1
            best_variant = historical_name

            for historical_variant in historical_variants:
                normalized_historical = normalize_name(
                    historical_variant
                )

                for fanta_variant in normalized_fanta_variants:
                    score = fuzz.WRatio(
                        fanta_variant,
                        normalized_historical,
                    )

                    if score > best_score:
                        best_score = score
                        best_variant = historical_variant

            candidate = history_row.copy()
            candidate["name_variants"] = historical_variants
            candidate["matched_name_variant"] = best_variant
            candidate["name_score"] = best_score

            season_candidates.append(candidate)

        # Select the best candidate rows, not the best individual aliases.
        season_candidates = sorted(
            season_candidates,
            key=lambda row: row["name_score"],
            reverse=True,
        )[:top_k]

        candidates.extend(season_candidates)

    candidates_df = pd.DataFrame(candidates).reset_index(drop=True)
    candidates_df.insert(0, "candidate_id", candidates_df.index)

    return candidates_df

def json_converter(value):
    """Convert NumPy and pandas values into JSON-compatible Python values."""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd.isna(value):
        return None
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
