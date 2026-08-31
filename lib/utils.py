import pandas as pd
import numpy as np
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


interest_markers = {
    "Da rivedere": "⚫",
    "Bassissimo": "⚪",
    "Basso": "🟡",
    "Medio": "🟠",
    "Alto": "🔴",
    "Scommessa": "🟣",
    "Buoni low cost": "🔵",
}

def set_format_interest(interest):
    if interest is None:
        return None
    marker = interest_markers.get(interest)
    return f"{marker} {interest}" if marker else interest

def highlight_player_role(row: pd.Series) -> list[str]:
    """Apply the Fantacalcio role color to every read-only player cell."""
    role_color = get_color_per_role(row.get("R", ""))
    if not role_color:
        return [""] * len(row)
    return [f"background-color: {role_color}; color: #212121"] * len(row)

def get_color_per_role(role: str) -> str:
    """Return a soft Material Design color for a Fantacalcio role."""
    role_colors_dict = {
        "P": "#EACD6D",  # Previous: "#FFD54F"
        "D": "#8FCD92",  # Previous: "#81C784"
        "C": "#73B3E7",  # Previous: "#64B5F6"
        "A": "#DE7D7D",  # Previous: "#E57373"
    }
    return role_colors_dict.get(str(role).strip().upper(), "")


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
