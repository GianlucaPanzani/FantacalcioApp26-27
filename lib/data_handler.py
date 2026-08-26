import numpy as np
import kagglehub
import re
import pandas as pd
from unidecode import unidecode
import unicodedata
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein


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

def download_dataset(out_dir: str, path_kaggle: str) -> None:
    kagglehub.dataset_download(
        path_kaggle,
        output_dir=out_dir
    )


def divide_values_by_denominator(values, denominator):
    """
    Divide two Series and replace invalid results with NaN.

    Parameters
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

    Parameters
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

    Parameters
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

    Parameters
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

    Parameters
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

    Parameters
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

def normalize_player_name(name):
    """
    Normalize a player name for matching.

    The function removes accents, duplicated spaces, case differences and
    punctuation, while preserving periods used in abbreviated names.

    Parameters
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

    Parameters
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

    Parameters
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
