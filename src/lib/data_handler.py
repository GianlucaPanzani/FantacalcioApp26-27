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
_GUEST_SETTING_KEYS = {
    "settings_my_manager_key", "settings_ai_enabled_key",
    *(f"settings_{role}_{field}_key" for role in "PDCA"
      for field in ("budget_limit", "graphical_cols")),
    *(f"selection_{field}_key" for field in ("Nome", "Squadra", "R")),
    *(f"statistics_{field}_key" for field in (
        "season", "competition", "team", "nineties", "fanta_role",
        "goals_per90", "player", "number_of_players", "seasons_to_plot", "role",
    )),
    *(f"fantacalcio_{field}_key" for field in (
        "player", "team", "fanta_role", "enable_player_preferences",
        "enable_ai_predictions", "show_ai_predictions", "show_ai_explainations",
        "show_ai_plots", "hide_other_fantamanagers", "bought_players_stats",
    )),
    "fantacalcio_fanta_managers_split_value",
}
_GUEST_SELECTION_PATH = Path("data/csv/pages/selection/selection_selected_players.csv")
_GUEST_ARCHIVE_FILES = {"manifest.json", "personal.env", "selection_selected_players.csv"}
_GUEST_ARCHIVE_LIMIT = 10 * 1024 * 1024
_GUEST_PLAYER_KEY = re.compile(r"selection_(selected|mln|interest|description)_\d+_key(?:_type)?$")


def _read_guest_env(content: str, *, strict: bool = False) -> dict[str, str]:
    """Read the app's KEY/value + KEY_type format without loading credentials."""
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            if strict:
                raise ValueError("Invalid personal.env line.")
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if strict and key in values:
            raise ValueError("Duplicate personal.env key.")
        values[key] = value.strip().strip('"').strip("'")
    return values


def _validate_guest_settings_zip_data(values: dict[str, str]) -> dict:
    """Validate allowlisted settings while retaining the existing type encoding."""
    decoded = {}
    for key in values:
        base_key = key.removesuffix("_type")
        if base_key not in _GUEST_SETTING_KEYS or base_key not in values:
            raise ValueError(f"Unsupported personal setting: {key}")
        if key.endswith("_type"):
            continue
        raw = values[key]
        value_type = values.get(f"{key}_type", "str")
        try:
            if value_type == "str":
                value = raw
            elif value_type == "bool" and raw.lower() in {"true", "false"}:
                value = raw.lower() == "true"
            elif value_type == "int":
                value = int(raw)
            elif value_type == "float":
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError
            elif value_type in {"list", "tuple"}:
                value = [item.strip() for item in raw.split(",") if item.strip()]
                if value_type == "tuple":
                    value = tuple(value)
            elif value_type in {"None", "NoneType"} and not raw:
                value = None
            else:
                raise ValueError
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Invalid value or type for {key}.") from exc

        if key == "settings_my_manager_key":
            valid = isinstance(value, str) and 0 < len(value.strip()) <= 200
        elif key.endswith("_budget_limit_key"):
            valid = type(value) is int and 0 <= value <= 1000
        elif key.endswith("_graphical_cols_key"):
            valid = isinstance(value, list)
        elif key in {
            "statistics_number_of_players_key", "statistics_seasons_to_plot_key",
            "fantacalcio_fanta_managers_split_value",
        }:
            maximum = {
                "statistics_number_of_players_key": 4,
                "statistics_seasons_to_plot_key": 10,
                "fantacalcio_fanta_managers_split_value": 5,
            }[key]
            valid = type(value) is int and 1 <= value <= maximum
        elif key in {"statistics_nineties_key", "statistics_goals_per90_key"}:
            valid = type(value) in {int, float} and 0 <= value <= 1_000_000
        elif key == "settings_ai_enabled_key" or any(part in key for part in (
            "enable_", "show_", "hide_", "bought_players_stats",
        )):
            valid = type(value) is bool
        else:
            valid = value is None or isinstance(value, (str, list, tuple))
        if not valid or len(raw) > 100_000:
            raise ValueError(f"Invalid personal setting: {key}")
        decoded[key] = value
    return decoded


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
    target = Path(env_values.get("selection_selected_players_csv_path_key", str(_GUEST_SELECTION_PATH)))
    target = (src_dir / target).resolve()
    if not target.is_relative_to(src_dir) or target.suffix.lower() != ".csv":
        raise ValueError("The local selection CSV must be inside src_dir.")
    protected_names = {"fantacalcio_bought_players.csv", "settings_fantacalcio_bought_players.csv"}
    if target.name in protected_names:
        raise ValueError("The selection path cannot refer to purchased players.")
    return target


def export_guest_state(src_dir: str | Path | None = None) -> bytes:
    """Build a downloadable ZIP of persisted personal settings and shortlist.

    The archive contains ``personal.env`` (an allowlisted subset of ``.env``),
    ``selection_selected_players.csv`` and a versioned manifest. It excludes
    purchases, participants, official auction rules, dataset paths and secrets.
    An absent shortlist is exported as an empty CSV. ``src_dir`` defaults to
    this project's src directory, independently of the working directory.

    This exports files already saved on disk, not unsaved Session State values.
    The returned bytes can be passed directly to ``st.download_button``.
    """
    root = Path(src_dir).resolve() if src_dir is not None else Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    env_values = _read_guest_env(env_path.read_text(encoding="utf-8") if env_path.exists() else "")
    personal_values = {
        key: value for key, value in env_values.items()
        if key.removesuffix("_type") in _GUEST_SETTING_KEYS
    }
    _validate_guest_settings_zip_data(personal_values)
    selection_path = _guest_selection_target(root, env_values)
    if selection_path.exists() and selection_path.stat().st_size > _GUEST_ARCHIVE_LIMIT:
        raise ValueError("Selection CSV is too large.")
    selection_bytes, _ = _validate_guest_selection_zip_data(
        selection_path.read_bytes() if selection_path.exists()
        else b"Id,mln,interest,description\n"
    )
    personal_content = "".join(f"{key}={value}\n" for key, value in personal_values.items())
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps({"format": "fantacalcio-guest-state", "version": 1}))
        archive.writestr("personal.env", personal_content)
        archive.writestr("selection_selected_players.csv", selection_bytes)
    return payload.getvalue()


def restore_guest_state(archive: bytes | BinaryIO, src_dir: str | Path | None = None) -> dict:
    """Validate a guest ZIP, merge personal .env keys and replace the shortlist.

    Use this on the guest's local installation (or a separate guest directory),
    never against the shared host .env for every account. Purchases and official
    rules are left untouched; account association belongs to the future backend.
    All archive members and values are validated before any file is written.
    Each destination is replaced atomically, with rollback on a write failure;
    this is a local restore operation, not a concurrent database transaction.

    The returned ``settings`` contains decoded values and ``selected_players``
    their count. Restart/reload the Streamlit session after import: load_env
    keeps existing Session State values. If integrating a restore callback,
    clear selection_* state and imported settings plus their widget keys before
    rerunning, so old selections cannot overwrite the restored CSV.
    """
    content = archive if isinstance(archive, bytes) else archive.read(_GUEST_ARCHIVE_LIMIT + 1)
    if len(content) > _GUEST_ARCHIVE_LIMIT:
        raise ValueError("Guest archive is too large.")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as bundle:
            members = bundle.infolist()
            if len(members) != 3 or {item.filename for item in members} != _GUEST_ARCHIVE_FILES:
                raise ValueError("Unexpected or missing guest archive files.")
            if any(item.flag_bits & 1 for item in members):
                raise ValueError("Encrypted archives are not supported.")
            if sum(item.file_size for item in members) > _GUEST_ARCHIVE_LIMIT:
                raise ValueError("Uncompressed guest archive is too large.")
            manifest = json.loads(bundle.read("manifest.json"))
            if manifest != {"format": "fantacalcio-guest-state", "version": 1}:
                raise ValueError("Unsupported guest archive format or version.")
            personal_values = _read_guest_env(bundle.read("personal.env").decode("utf-8"), strict=True)
            settings = _validate_guest_settings_zip_data(personal_values)
            selection_bytes, selection_count = _validate_guest_selection_zip_data(bundle.read("selection_selected_players.csv"))
    except (zipfile.BadZipFile, UnicodeError, csv.Error, json.JSONDecodeError, NotImplementedError) as exc:
        raise ValueError("Invalid guest archive.") from exc

    root = Path(src_dir).resolve() if src_dir is not None else Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    original_env = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    selection_path = _guest_selection_target(root, _read_guest_env(original_env))
    retained_lines = []
    for line in original_env.splitlines(keepends=True):
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        # The CSV is authoritative; remove stale per-player copies and flags.
        if (key.removesuffix("_type") in settings or _GUEST_PLAYER_KEY.fullmatch(key)
                or key.removesuffix("_type") == "selection_selection_players_restored_v2_key"):
            continue
        retained_lines.append(line)
    merged_env = "".join(retained_lines)
    if merged_env and not merged_env.endswith("\n"):
        merged_env += "\n"
    merged_env += "".join(f"{key}={value}\n" for key, value in personal_values.items())

    replacements = {env_path: merged_env.encode("utf-8"), selection_path: selection_bytes}
    originals = {path: path.read_bytes() if path.exists() else None for path in replacements}
    staged = {}
    applied = []
    try:
        for path, data in replacements.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
                staged[path] = Path(temporary.name)
                temporary.write(data)
        for path, temporary_path in staged.items():
            os.replace(temporary_path, path)
            applied.append(path)
    except OSError:
        for path in reversed(applied):
            if originals[path] is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(originals[path])
        raise
    finally:
        for temporary_path in staged.values():
            temporary_path.unlink(missing_ok=True)
    return {"settings": settings, "selected_players": selection_count}


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
