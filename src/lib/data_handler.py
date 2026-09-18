import numpy as np
import kagglehub
import re
import pandas as pd
from unidecode import unidecode
import unicodedata
import csv
import io
import json
import math
import os
from pathlib import Path
import tempfile
from typing import BinaryIO
import zipfile
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

from backend import db_api
from backend.persistent_state_db import (
    get_persistent_state,
    get_persistent_states,
    rm_persistent_states,
    set_persistent_state,
    update_persistent_state,
)


# ========================================================
#                   DATA STRUCTURES
# ========================================================

# Common name: (column in 2017-25 dataset, column in 2025-26 dataset)
COLUMN_MAP = {
    # Player information
    "player": ("player", "Player"),
    "team": ("team", "Squad"),
    "competition": ("league", "Comp"),
    "nationality": ("nation", "Nation"),
    "position": ("pos", "Pos"),
    "age": ("age_fbref", "Age"),
    "birth_year": ("born_fbref", "Born"),

    # Playing time
    "appearances": ("Playing Time_MP", "MP"),
    "starts": ("Playing Time_Starts", "Starts"),
    "minutes": ("Playing Time_Min", "Min"),
    "nineties": ("Playing Time_90s", "90s"),

    # Offensive statistics
    "goals_per90": ("Per 90 Minutes_Gls", "Gls"),
    "assists_per90": ("Per 90 Minutes_Ast", "Ast"),
    "goals_assists_per90": ("Per 90 Minutes_G+A", "G+A"),
    "non_penalty_goals_per90": ("Per 90 Minutes_G-PK", "G-PK"),
    "non_penalty_goals_assists_per90": (
        "Per 90 Minutes_G+A-PK",
        "G+A-PK",
    ),
    "penalty_attempts_per90": ("Per 90 Minutes_PKatt", "PKatt"),

    # Discipline
    "yellow_cards_per90": ("Per 90 Minutes_CrdY", "CrdY"),
    "red_cards_per90": ("Per 90 Minutes_CrdR", "CrdR"),

    # Shooting
    "shots_on_target_pct": ("Standard_SoT%", "SoT%"),
    "shots_per90": ("Standard_Sh/90", "Sh/90"),
    "shots_on_target_per90": ("Standard_SoT/90", "SoT/90"),
    "goals_per_shot": ("Standard_G/Sh", "G/Sh"),
    "goals_per_shot_on_target": ("Standard_G/SoT", "G/SoT"),

    # Defensive statistics
    "interceptions_per90": ("Per 90 Minutes_Int", "Int"),
    "tackles_won_per90": ("Per 90 Minutes_Tackles_TklW", "TklW"),

    # Goalkeeper statistics
    "goals_against_per90": ("Performance_GA90", "GA90"),
    "shots_on_target_against_per90": (
        "Per 90 Minutes_Performance_SoTA",
        "SoTA",
    ),
    "saves_per90": ("Per 90 Minutes_Performance_Saves", "Saves"),
    "save_pct": ("Performance_Save%", "Save%"),
    "wins_per90": ("Per 90 Minutes_Performance_W", "W"),
    "draws_per90": ("Per 90 Minutes_Performance_D", "D"),
    "losses_per90": ("Per 90 Minutes_Performance_L", "L"),
    "clean_sheets_per90": ("Per 90 Minutes_Performance_CS", "CS"),
    "clean_sheet_pct": ("Performance_CS%", "CS%"),
    "keeper_penalty_attempts_per90": (
        "Per 90 Minutes_Penalty Kicks_PKatt",
        "PKatt_stats_keeper",
    ),
    "penalties_allowed_per90": (
        "Per 90 Minutes_Penalty Kicks_PKA",
        "PKA",
    ),
    "penalties_saved_per90": (
        "Per 90 Minutes_Penalty Kicks_PKsv",
        "PKsv",
    ),
    "penalties_missed_per90": (
        "Per 90 Minutes_Penalty Kicks_PKm",
        "PKm",
    ),
}

# Columns containing totals in the 2025-26 dataset.
# They must be divided by the number of 90-minute units.
TOTALS_IN_2025_26 = {
    "goals_per90",
    "assists_per90",
    "goals_assists_per90",
    "non_penalty_goals_per90",
    "penalty_attempts_per90",
    "yellow_cards_per90",
    "red_cards_per90",
    "interceptions_per90",
    "tackles_won_per90",
    "shots_on_target_against_per90",
    "saves_per90",
    "wins_per90",
    "draws_per90",
    "losses_per90",
    "clean_sheets_per90",
    "keeper_penalty_attempts_per90",
    "penalties_allowed_per90",
    "penalties_saved_per90",
    "penalties_missed_per90",
}


# ====================================================================================
#                           DATA HANDLING FUNCTIONS
# ====================================================================================

# Only personal preferences may travel between a guest's app and an auction.
# Official budgets, squad limits, purchases, paths and credentials stay local.
_GUEST_PERMANENT_STATE_KEYS = {
    "settings_my_manager_key",
    "settings_ai_enabled_key",
    "settings_P_budget_limit_widget_key",
    "settings_D_budget_limit_widget_key",
    "settings_C_budget_limit_widget_key",
    "settings_A_budget_limit_widget_key",
    "settings_P_graphical_cols_key",
    "settings_D_graphical_cols_key",
    "settings_C_graphical_cols_key",
    "settings_A_graphical_cols_key",
    "selection_Nome_key",
    "selection_Squadra_widget_key",
    "selection_R_widget_key",
    "statistics_season_key",
    "statistics_competition_key",
    "statistics_team_key",
    "statistics_nineties_key",
    "statistics_fanta_role_key",
    "statistics_goals_per90_key",
    "statistics_player_key",
    "statistics_number_of_players_key",
    "statistics_seasons_to_plot_key",
    "statistics_role_key",
    "fantacalcio_player_widget_key",
    "fantacalcio_team_widget_key",
    "fantacalcio_fanta_role_widget_key",
    "fantacalcio_enable_player_preferences_key",
    "fantacalcio_enable_ai_predictions_key",
    "fantacalcio_show_ai_predictions_key",
    "fantacalcio_show_ai_explainations_key",
    "fantacalcio_show_ai_plots_key",
    "fantacalcio_hide_other_fantamanagers_key",
    "fantacalcio_bought_players_stats_key",
    "fantacalcio_fanta_managers_split_value_widget_key",
}
_GUEST_SELECTION_PATH = Path(
    "data/csv/pages/selection/selection_selected_players.csv"
)
_GUEST_ARCHIVE_FILES = {
    "manifest.json",
    "persistent_state.json",
    "selection_selected_players.csv",
}
_GUEST_ARCHIVE_LIMIT_BYTES = 10_485_760  # 10 MiB
_GUEST_PLAYER_FIELDS = {
    "selected",
    "mln",
    "interest",
    "description",
}


def _is_guest_key_correct(key: str) -> bool:
    """Return whether a key stores one player's personal selection data."""
    parts = key.removesuffix("_type").split("_")
    return (
        len(parts) == 4
        and parts[0] == "selection"
        and parts[1] in _GUEST_PLAYER_FIELDS
        and parts[2].isdigit()
        and parts[3] == "key"
    )


def _validate_backup_persistent_state(values: dict) -> dict:
    """Validate the allowlisted persistent values stored in a backup."""
    if not isinstance(values, dict):
        raise ValueError("persistent_state.json must contain a JSON object.")
    validated = {}
    for key, value in values.items():
        if not isinstance(key, str) or key not in _GUEST_PERMANENT_STATE_KEYS:
            raise ValueError(f"Unsupported personal setting: {key}")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"Invalid personal setting: {key}")
        if key == "settings_my_manager_key":
            valid = isinstance(value, str) and 0 < len(value.strip()) <= 200
        elif key.endswith("_budget_limit_widget_key"):
            valid = type(value) is int and 0 <= value <= 1000
        elif key.endswith("_graphical_cols_key"):
            valid = isinstance(value, list)
        elif key in {
            "statistics_number_of_players_key", "statistics_seasons_to_plot_key",
            "fantacalcio_fanta_managers_split_value_widget_key",
        }:
            maximum = {
                "statistics_number_of_players_key": 4,
                "statistics_seasons_to_plot_key": 10,
                "fantacalcio_fanta_managers_split_value_widget_key": 5,
            }[key]
            valid = type(value) is int and 1 <= value <= maximum
        elif key in {"statistics_nineties_key", "statistics_goals_per90_key"}:
            valid = type(value) in {int, float} and 0 <= value <= 1_000_000
        elif key == "settings_ai_enabled_key" or any(part in key for part in (
            "enable_", "show_", "hide_", "bought_players_stats",
        )):
            valid = type(value) is bool
        else:
            valid = value is None or isinstance(value, (str, list))
        if not valid or len(json.dumps(value, ensure_ascii=False)) > 100_000:
            raise ValueError(f"Invalid personal setting: {key}")
        validated[key] = value
    return validated


def _validate_guest_selection_zip_data(content: bytes) -> tuple[bytes, int]:
    """Normalize the current shortlist format and reject malformed player data."""
    columns = ["Id", "mln", "interest", "description"]
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
    if reader.fieldnames != columns:
        raise ValueError("Selection CSV must contain Id,mln,interest,description.")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    player_ids = set()
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("Invalid selection CSV row.")
        try:
            player_id = int(row["Id"])
            amount = int(row["mln"] or "0")
        except ValueError as exc:
            raise ValueError("Player IDs and spending limits must be integers.") from exc
        if not 0 < player_id <= 2**53 - 1 or player_id in player_ids:
            raise ValueError("Player IDs must be positive and unique.")
        if not 0 <= amount <= 1_000_000:
            raise ValueError("Spending limits must be nonnegative and at most 1000000.")
        if len(row["interest"]) > 100 or len(row["description"]) > 10_000:
            raise ValueError("Player interest or description is too long.")
        player_ids.add(player_id)
        if len(player_ids) > 10_000:
            raise ValueError("Too many selected players.")
        row.update(Id=player_id, mln=amount, interest=row["interest"] or "Da valutare")
        writer.writerow(row)
    return output.getvalue().encode("utf-8"), len(player_ids)


def _guest_selection_target(src_dir: Path, env_values: dict[str, str]) -> Path:
    """Honor a local shortlist path, never a path supplied by an imported ZIP."""
    target = Path(
        env_values.get(
            "selection_selected_players_csv_path_key",
            str(_GUEST_SELECTION_PATH),
        )
    )
    target = (src_dir / target).resolve()
    if not target.is_relative_to(src_dir) or target.suffix.lower() != ".csv":
        raise ValueError("The local selection CSV must be inside src_dir.")
    protected_names = {"fantacalcio_bought_players.csv", "settings_fantacalcio_bought_players.csv"}
    if target.name in protected_names:
        raise ValueError("The selection path cannot refer to purchased players.")
    return target


def export_guest_state(user_id: int, src_dir: str | Path | None = None) -> bytes:
    """Build a downloadable ZIP of persisted personal settings and shortlist.

    The archive contains ``persistent_state.json``, the selected-player CSV and
    a versioned manifest. It excludes
    purchases, Fanta Managers, official auction rules, dataset paths and secrets.
    An absent shortlist is exported as an empty CSV. ``src_dir`` defaults to
    this project's src directory, independently of the working directory.

    Values come from ``persistent_state`` rather than the local ``.env`` file.
    """
    root = Path(src_dir).resolve() if src_dir is not None else Path(__file__).resolve().parents[1]
    rows = get_persistent_states({"user_id": user_id})
    values = {row["key"]: json.loads(row["value_json"]) for row in rows}
    persistent_values = _validate_backup_persistent_state({
        key: value
        for key, value in values.items()
        if key in _GUEST_PERMANENT_STATE_KEYS
    })
    selection_path = _guest_selection_target(root, {
        "selection_selected_players_csv_path_key": values.get(
            "selection_selected_players_csv_path_key",
            str(_GUEST_SELECTION_PATH),
        )
    })
    if (
        selection_path.exists()
        and selection_path.stat().st_size > _GUEST_ARCHIVE_LIMIT_BYTES
    ):
        raise ValueError("Selection CSV is too large.")
    selection_bytes, _ = _validate_guest_selection_zip_data(
        selection_path.read_bytes() if selection_path.exists()
        else b"Id,mln,interest,description\n"
    )
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"format": "fantacalcio-persistent-state", "version": 1}),
        )
        archive.writestr(
            "persistent_state.json",
            json.dumps(persistent_values, ensure_ascii=False),
        )
        archive.writestr("selection_selected_players.csv", selection_bytes)
    return payload.getvalue()


def restore_guest_state(
    archive: bytes | BinaryIO,
    user_id: int,
    username: str,
    src_dir: str | Path | None = None,
) -> dict:
    """Restore a ZIP into the user's persistent DB state and personal CSV.

    Params
    ----------
    archive : bytes or BinaryIO
        Backup archive to validate and restore.
    user_id : int
        Identifier of the user receiving the restored state.
    username : str
        Username used for the selected-player CSV filename.
    src_dir : str, pathlib.Path or None
        Application data root, or the project ``src`` directory when omitted.

    Returns
    -------
    dict
        Restored settings, selected-player count and CSV path.
    """
    content = archive if isinstance(archive, bytes) else archive.read()
    return store_guest_archive(content, user_id, username, src_dir=src_dir)


def download_dataset(out_dir: str, path_kaggle: str) -> None:
    """Download a Kaggle dataset into the requested local directory.

    Params
    ----------
    out_dir : str
        Destination directory for downloaded files.
    path_kaggle : str
        Kaggle dataset identifier accepted by ``kagglehub``.
    """
    kagglehub.dataset_download(
        path_kaggle,
        output_dir=out_dir
    )


def divide_values_by_denominator(values, denominator):
    """
    Divide two Series and replace invalid results with NaN.

    Params
    ----------
    values : pandas.Series
        Values to divide.
    denominator : pandas.Series
        Division denominator.

    Returns
    -------
    pandas.Series
        Safely computed division results.
    """
    values = pd.to_numeric(values, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")

    result = values.div(denominator.replace(0, np.nan))
    return result.replace([np.inf, -np.inf], np.nan)


def convert_format_season(value):
    """
    Convert a compact season code such as 1718 into '2017-18'.
    """
    if pd.isna(value):
        return pd.NA

    code = str(int(value)).zfill(4)
    return f"20{code[:2]}-{code[2:]}"


def select_and_rename_columns(df, source_index):
    """
    Select shared columns and rename them using the common schema.

    Params
    ----------
    df : pandas.DataFrame
        Source dataset.
    source_index : int
        Use 0 for the 2017-25 dataset and 1 for the 2025-26 dataset.

    Returns
    -------
    pandas.DataFrame
        Dataset containing only standardized shared columns.
    """
    rename_map = {
        source_columns[source_index]: common_name
        for common_name, source_columns in COLUMN_MAP.items()
    }
    return df[list(rename_map)].rename(columns=rename_map).copy()


def preprocess_2017_2025(df):
    """
    Standardize the dataset containing seasons from 2017-18 to 2024-25.

    No competition filtering is applied.
    """
    result = select_and_rename_columns(df, source_index=0)
    season = df["season"].apply(convert_format_season)
    result.insert(0, "season", season.to_numpy())
    return result


def preprocess_2025_2026(df):
    """
    Standardize the 2025-26 dataset without filtering competitions.

    Statistics stored as season totals are converted to per-90 values
    to match the format used by the 2017-25 dataset.
    """
    result = select_and_rename_columns(df, source_index=1)
    result.insert(0, "season", "2025-26") # fixed season for every field

    num_of_nineties_played = pd.to_numeric(result["nineties"], errors="coerce")
    for column in TOTALS_IN_2025_26:
        result[column] = divide_values_by_denominator(
            values=result[column],
            denominator=num_of_nineties_played
        )

    # This field is already expressed per 90 in the source dataset.
    result["non_penalty_goals_assists_per90"] = pd.to_numeric(
        result["non_penalty_goals_assists_per90"],
        errors="coerce",
    )

    return result


def concat(dataset_2017_2025, dataset_2025_2026):
    """
    Standardize and concatenate all available player seasons.

    Params
    ----------
    dataset_2017_2025 : pandas.DataFrame
        FIFA-FBref dataset covering 2017-18 through 2024-25.
    dataset_2025_2026 : pandas.DataFrame
        Dataset covering the 2025-26 season.

    Returns
    -------
    pandas.DataFrame
        Unified dataset containing players from every competition.
    """
    old_data = preprocess_2017_2025(dataset_2017_2025)
    season_2025_26 = preprocess_2025_2026(dataset_2025_2026)
    return pd.concat(
        [old_data, season_2025_26],
        ignore_index=True,
    )


def name_similarity(history_name, fanta_name):
    """
    Calculate the similarity between a complete and an abbreviated name.

    Params
    ----------
    history_name : str
        Name from the historical dataset.
    fanta_name : str
        Name from the Fantacalcio dataset.

    Returns
    -------
    float
        Similarity score between 0 and 100.
    """
    history_name = normalize_player_name(history_name)
    fanta_name = normalize_player_name(fanta_name)

    if not history_name or not fanta_name:
        return 0.0

    # Exact match after normalization.
    if history_name == fanta_name:
        return 100.0

    # Automatically accept one or two character differences.
    if Levenshtein.distance(history_name, fanta_name) <= 2:
        return 99.0

    # Useful when the Fantacalcio name contains only the surname.
    history_tokens = set(history_name.split())
    fanta_tokens = set(fanta_name.split())

    if fanta_tokens.issubset(history_tokens):
        return 98.0

    # Handles different token orders and abbreviated names.
    return max(
        fuzz.WRatio(history_name, fanta_name),
        fuzz.token_set_ratio(history_name, fanta_name),
    )


def find_best_player_match(
    history_name,
    fanta_names,
    minimum_score=85,
):
    """
    Find the best Fantacalcio match for one historical player.

    Params
    ----------
    history_name : str
        Player name from the historical dataset.
    fanta_names : iterable of str
        Available names in the Fantacalcio list.
    minimum_score : float, default=85
        Minimum similarity required to accept a match.

    Returns
    -------
    tuple
        Best matched name and similarity score. The matched name is None
        when the minimum score is not reached.
    """
    best_name = None
    best_score = 0.0

    for fanta_name in fanta_names:
        score = name_similarity(history_name, fanta_name)

        if score > best_score:
            best_name = fanta_name
            best_score = score

    if best_score < minimum_score:
        return None, best_score

    return best_name, best_score


def filter_history_by_fantacalcio_players(
    history_df,
    fanta_df,
    history_name_col="player",
    fanta_name_col="Nome",
    minimum_score=85,
):
    """
    Keep historical records only for players in the Fantacalcio dataset.

    All historical seasons of a matched player are retained.

    Params
    ----------
    history_df : pandas.DataFrame
        Historical player dataset.
    fanta_df : pandas.DataFrame
        Current Fantacalcio player list.
    history_name_col : str, default='player'
        Player-name column in the historical dataset.
    fanta_name_col : str, default='Nome'
        Player-name column in the Fantacalcio dataset.
    minimum_score : float, default=85
        Minimum fuzzy similarity required to accept a match.

    Returns
    -------
    filtered_history : pandas.DataFrame
        Historical observations belonging to matched players.
    matches : pandas.DataFrame
        Matching table containing names and similarity scores.
    """
    fanta_names = (
        fanta_df[fanta_name_col]
        .dropna()
        .astype(str)
        .unique()
    )

    historical_names = (
        history_df[history_name_col]
        .dropna()
        .astype(str)
        .unique()
    )

    matches = []
    for history_name in historical_names:
        matched_name, score = find_best_player_match(
            history_name,
            fanta_names,
            minimum_score,
        )

        matches.append({
            "history_player": history_name,
            "fanta_player": matched_name,
            "match_score": round(score, 2),
            "matched": matched_name is not None,
        })

    matches = pd.DataFrame(matches)

    valid_names = matches.loc[
        matches["matched"],
        "history_player",
    ]

    filtered_history = history_df[
        history_df[history_name_col].isin(valid_names)
    ].copy()

    # Add the corresponding Fantacalcio name.
    name_mapping = matches.set_index(
        "history_player"
    )["fanta_player"]

    filtered_history["fanta_player"] = (
        filtered_history[history_name_col].map(name_mapping)
    )

    return filtered_history, matches

def normalize_name(name: str) -> str:
    """Normalize a player name for fuzzy comparison."""
    name = unicodedata.normalize("NFD", str(name))
    name = "".join(
        char for char in name if unicodedata.category(char) != "Mn"
    )
    name = re.sub(r"[^\w\s.]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def generate_name_variants(full_name: str) -> list[str]:
    """Generate common full-name and abbreviated-name representations.

    Params
    ----------
    full_name : str
        Player name to expand into matching variants.

    Returns
    -------
    list of str
        Unique variants in deterministic order.
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

    if len(parts[-1].replace(".", "")) == 1:
        initial = parts[-1].replace(".", "")
        surname_first = " ".join(parts[:-1])
        variants.extend([f"{initial}. {surname_first}", surname_first])

    return list(dict.fromkeys(variants))


def get_candidates_by_season(
    fanta_name: str,
    history_df: pd.DataFrame,
    top_k: int = 3,
    season_column: str = "season",
    name_column: str = "player",
) -> pd.DataFrame:
    """Select the best historical name candidates for each season.

    Params
    ----------
    fanta_name : str
        Fantacalcio player name to match.
    history_df : pandas.DataFrame
        Historical player rows grouped by season during matching.
    top_k : int
        Maximum candidates retained for each season.
    season_column : str
        Column containing season labels.
    name_column : str
        Column containing historical player names.

    Returns
    -------
    pandas.DataFrame
        Candidate rows with identifiers, variants and fuzzy-match scores.
    """
    fanta_variants = generate_name_variants(fanta_name) or [fanta_name]
    normalized_fanta_variants = [normalize_name(name) for name in fanta_variants]

    candidates = []
    for _, season_df in history_df.groupby(season_column, sort=False):
        season_candidates = []
        for _, history_row in season_df.iterrows():
            historical_name = str(history_row.get(name_column, ""))
            historical_variants = generate_name_variants(historical_name)
            best_score = -1
            best_variant = historical_name

            for historical_variant in historical_variants:
                normalized_historical = normalize_name(historical_variant)
                for fanta_variant in normalized_fanta_variants:
                    score = fuzz.WRatio(fanta_variant, normalized_historical)
                    if score > best_score:
                        best_score = score
                        best_variant = historical_variant

            candidate = history_row.copy()
            candidate["name_variants"] = historical_variants
            candidate["matched_name_variant"] = best_variant
            candidate["name_score"] = best_score
            season_candidates.append(candidate)

        candidates.extend(
            sorted(
                season_candidates,
                key=lambda row: row["name_score"],
                reverse=True,
            )[:top_k]
        )

    candidates_df = pd.DataFrame(candidates).reset_index(drop=True)
    candidates_df.insert(0, "candidate_id", candidates_df.index)
    return candidates_df


def normalize_player_name(name):
    """
    Normalize a player name for matching.

    The function removes accents, duplicated spaces, case differences and
    punctuation, while preserving periods used in abbreviated names.

    Params
    ----------
    name : object
        Original player name.

    Returns
    -------
    str
        Normalized player name.
    """

    special_chars_map = {
        "ı": "i",
        "ł": "l",
        "ø": "o",
        "á": "a",
        "ó": "o",
        "ž": "z",
        "ć": "c",
        "-": " ",
    }

    name = unidecode(str(name)).lower().strip()
    name = "".join(char for char in unicodedata.normalize("NFD", name) if unicodedata.category(char) != "Mn")
    name = "".join(special_chars_map.get(char, char) for char in name)

    # Preserve periods because they identify abbreviated names
    name = re.sub(r"[^a-z0-9.\s]", " ", name)
    name = re.sub(r"\s+", " ", name)

    return name.strip()


def filter_history_exact_matches(
    history_df,
    fanta_df,
    history_name_col="player",
    fanta_name_col="Nome",
):
    """
    Filter the historical dataset using exact or abbreviated name matches.

    Exact normalized names are matched directly. Fantacalcio names written as
    "Surname N." are matched when the surname appears as a complete sequence
    of words in the historical player name.

    Multiple historical players may be retained for an abbreviated name. The
    user can subsequently resolve ambiguous matches through the interface.

    Params
    ----------
    history_df : pandas.DataFrame
        Historical player dataset.
    fanta_df : pandas.DataFrame
        Current Fantacalcio player list.
    history_name_col : str, default='player'
        Player-name column in the historical dataset.
    fanta_name_col : str, default='Nome'
        Player-name column in the Fantacalcio dataset.

    Returns
    -------
    filtered_history : pandas.DataFrame
        Historical rows belonging to matched players.
    unmatched : pandas.DataFrame
        Fantacalcio players for which no historical match was found.
    """
    history = history_df.copy()
    fanta = fanta_df.copy()

    history["normalized_name"] = history[history_name_col].apply(normalize_player_name)
    fanta["normalized_name"] = fanta[fanta_name_col].apply(normalize_player_name)

    history_names = set(history["normalized_name"])
    valid_history_names = set()
    matched_positions = []

    for _, fanta_row in fanta.iterrows():
        original_name = str(fanta_row[fanta_name_col]).strip()
        normalized_name = fanta_row["normalized_name"]
        row_matches = set()

        # Standard exact normalized-name match.
        if normalized_name in history_names:
            row_matches.add(normalized_name)

        matched_positions.append(bool(row_matches))
        valid_history_names.update(row_matches)

    matched_mask = pd.Series(matched_positions, index=fanta.index)

    unmatched = fanta.loc[~matched_mask].copy()
    filtered_history = history[history["normalized_name"].isin(valid_history_names)].copy()

    filtered_history.drop(columns="normalized_name", inplace=True)
    unmatched.drop(columns="normalized_name", inplace=True)

    return filtered_history, unmatched


def filter_history_relaxed_matches(
    history_df,
    fanta_df,
    history_name_col="player",
    fanta_name_col="Nome",
):
    """
    Add a normalized join key to the historical and Fantacalcio datasets.

    Exact normalized names are matched directly. Fantacalcio names written as
    "Surname N." are matched when the surname appears as a complete sequence
    of words in a historical player name.

    When an abbreviated name matches multiple historical players, the
    Fantacalcio row is duplicated once for each possible match.

    Params
    ----------
    history_df : pandas.DataFrame
        Historical player dataset.
    fanta_df : pandas.DataFrame
        Current Fantacalcio player list.
    history_name_col : str, default='player'
        Player-name column in the historical dataset.
    fanta_name_col : str, default='Nome'
        Player-name column in the Fantacalcio dataset.

    Returns
    -------
    history_normalized_df : pandas.DataFrame
        Complete historical dataset with the normalized_name column.
    fanta_normalized_df : pandas.DataFrame
        Complete Fantacalcio dataset with normalized_name containing the
        corresponding historical join key.
    """

    history_normalized_df = history_df.copy()
    fanta_normalized_df = fanta_df.copy()

    # Add the common "normalized_name" field
    history_normalized_df["normalized_name"] = (
        history_normalized_df[history_name_col]
        .fillna("")
        .apply(normalize_player_name)
    )
    fanta_normalized_df["normalized_name"] = (
        fanta_normalized_df[fanta_name_col]
        .fillna("")
        .apply(normalize_player_name)
    )

    history_names = {name for name in history_normalized_df["normalized_name"] if name}

    def relaxed_matching_rules(normalized_name):
        """Return historical names compatible with a normalized short name."""
        # Match exact normalized names.
        if normalized_name in history_names:
            return {normalized_name}

        # Match names written as "Surname N.".
        if "." in normalized_name:
            # Every token before the final initial belongs to the surname.
            surname = " ".join(normalized_name.split()[:-1])
            return {
                history_name
                for history_name in history_names
                if surname and f" {surname} " in f" {history_name} "
            }
        
        # Match names containing only the surname.
        return {
            history_name
            for history_name in history_names
            if normalized_name
            and f" {normalized_name} " in f" {history_name} "
        }

    matched_records = []
    matched_indices = []

    for index, fanta_row in fanta_normalized_df.iterrows():
        normalized_name = fanta_row["normalized_name"]
        row_matches = relaxed_matching_rules(normalized_name)

        if row_matches:
            # Create one row for every possible historical join key.
            for matched_name in sorted(row_matches):
                matched_row = fanta_row.copy()
                matched_row["normalized_name"] = matched_name
                matched_records.append(matched_row)
                matched_indices.append(index)
        else:
            # Preserve unmatched players in the returned dataset.
            matched_records.append(fanta_row.copy())
            matched_indices.append(index)

    if matched_records:
        fanta_normalized_df = pd.DataFrame(matched_records, index=matched_indices)
        fanta_normalized_df.index.name = fanta_df.index.name

    return history_normalized_df, fanta_normalized_df


def parse_guest_archive(archive: bytes) -> dict:
    """Validate and decode a personal backup without writing local files.

    Params
    ----------
    archive : bytes
        ZIP archive generated by :func:`export_guest_state`.

    Returns
    -------
    dict
        Decoded personal settings and the validated selected-players CSV.
    """
    if len(archive) > _GUEST_ARCHIVE_LIMIT_BYTES:
        raise ValueError("Guest archive is too large.")

    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            members = bundle.infolist()
            if (
                len(members) != len(_GUEST_ARCHIVE_FILES)
                or {item.filename for item in members} != _GUEST_ARCHIVE_FILES
            ):
                raise ValueError("Unexpected or missing guest archive files.")
            if any(item.flag_bits & 1 for item in members):
                raise ValueError("Encrypted archives are not supported.")
            if sum(item.file_size for item in members) > _GUEST_ARCHIVE_LIMIT_BYTES:
                raise ValueError("Uncompressed guest archive is too large.")

            manifest = json.loads(bundle.read("manifest.json"))
            if manifest != {
                "format": "fantacalcio-persistent-state",
                "version": 1,
            }:
                raise ValueError("Unsupported guest archive format or version.")

            persistent_values = json.loads(
                bundle.read("persistent_state.json").decode("utf-8")
            )
            settings = _validate_backup_persistent_state(persistent_values)
            selection_bytes, selection_count = _validate_guest_selection_zip_data(
                bundle.read("selection_selected_players.csv")
            )
    except (
        zipfile.BadZipFile,
        UnicodeError,
        csv.Error,
        json.JSONDecodeError,
        NotImplementedError,
    ) as exc:
        raise ValueError("Invalid guest archive.") from exc

    return {
        "settings": settings,
        "selection_csv": selection_bytes,
        "selected_players": selection_count,
    }


def store_guest_archive(
    archive: bytes,
    user_id: int,
    username: str,
    connection=None,
    src_dir: str | Path | None = None,
) -> dict:
    """Store a validated backup in persistent state and the user's CSV file.

    Params
    ----------
    archive : bytes
        ZIP backup generated by :func:`export_guest_state`.
    user_id : int
        Identifier of the user receiving the restored data.
    username : str
        Username used for the personal selected-player CSV filename.
    connection : sqlite3.Connection or None
        Active database transaction to reuse, when provided.
    src_dir : str or pathlib.Path or None
        Application data root, or the project ``src`` directory when omitted.

    Returns
    -------
    dict
        Restored settings and number of selected players.
    """
    backup = parse_guest_archive(archive)
    root = (
        Path(src_dir).resolve()
        if src_dir is not None
        else Path(__file__).resolve().parents[1]
    )
    selection_dir = root / "data/csv/pages/selection"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_path = selection_dir / f"selection_selected_players_{username}.csv"
    stored_path = selection_path.relative_to(root).as_posix()

    def store_rows(active_connection):
        current_rows = get_persistent_states(
            {"user_id": user_id},
            connection=active_connection,
        )
        for row in current_rows:
            if (
                row["key"] in _GUEST_PERMANENT_STATE_KEYS
                or _is_guest_key_correct(row["key"])
                or row["key"] == "selection_selected_players_csv_path_key"
            ):
                rm_persistent_states(
                    {
                        "user_id": user_id,
                        "page_name": row["page_name"],
                        "key": row["key"],
                    },
                    connection=active_connection,
                )

        restored_values = {
            **backup["settings"],
            "selection_selected_players_csv_path_key": stored_path,
        }
        for key, value in restored_values.items():
            set_persistent_state(
                {
                    "user_id": user_id,
                    "page_name": key.split("_", 1)[0],
                    "key": key,
                    "value_json": json.dumps(value, ensure_ascii=False),
                },
                connection=active_connection,
            )

    if connection is None:
        with db_api.transaction() as active_connection:
            store_rows(active_connection)
    else:
        store_rows(connection)

    with tempfile.NamedTemporaryFile(dir=selection_dir, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        temporary.write(backup["selection_csv"])
    try:
        os.replace(temporary_path, selection_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "settings": backup["settings"],
        "selected_players": backup["selected_players"],
        "selection_csv_path": stored_path,
    }
