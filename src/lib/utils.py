from datetime import datetime
import hashlib
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import streamlit as st
from backend.auctions_db import get_auctions


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
    "team": "Team",
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
    "Squadra": "Current team",
    "Qt.A": "Quote",
    "Qt.I": "Initial quote",
    "Diff.": "Quote diff.",
    "Qt.A M": "Mantra quote",
    "Qt.I M": "Initial Mantra quote",
    "Diff.M": "Mantra quote diff.",
    "FVM": "Mean Fanta mln",
    "FVM M": "Mean Mantra mln",
}

interest_colors_dict = {
    "Da valutare": "#979797",   # Gray: not yet evaluated
    "Bassissimo": "#FFF8B8",    # Pale yellow: very low interest
    "Basso": "#FFE365",         # Yellow: low interest
    "Medio": "#F8AB39",         # Orange: medium interest
    "Alto": "#FB7272",          # Soft red: high interest
    "Altissimo": "#F55050",     # Stronger red: very high interest
    "Scommessa": "#DA74EC",     # Light purple: speculative pick
    "Buoni low cost": "#84E7A0", # Mint green: good budget pick
}

def get_role_icon(fanta_role: str):
    """Return the emoji associated with a Fantacalcio role code."""
    role_icons = {
        "P": "🧤",
        "D": "🛡️",
        "C": "⚽",
        "A": "🎯"
    }
    return role_icons[fanta_role]

def get_current_year():
    """Return the current calendar year."""
    return datetime.now().year

def get_current_date():
    """Return the current local calendar date."""
    return datetime.now().date().isoformat()

def get_current_season():
    """Return the season starting in the current calendar year."""
    year = get_current_year()
    return f"{year}-{str(year+1)[2:]}"

def get_six_digits_rnd_number():
    return f"{secrets.randbelow(1_000_000):06d}"

def get_hash_sha256(string: str):
    return hashlib.sha256(string.encode("utf-8")).hexdigest()

def generate_unique_auction_code():
    """Generate and store an unused auction code and its hash."""
    for _ in range(10000):
        # Generate a random 6-digits code
        auction_code = get_six_digits_rnd_number()
        auction_code_hash = get_hash_sha256(auction_code)

        if not get_auctions(
            filters={"auction_code_hash": auction_code_hash},
            proj=["id"],
        ):
            return auction_code, auction_code_hash
        
    raise Exception("Auction code not generated correctly")


def get_auction_link(auction_code: str) -> str:
    """Build the public application URL containing an auction code.

    Params
    ----------
    auction_code : str
        Six-digit code of the auction to join.

    Returns
    -------
    str
        Current application URL with the auction code as a query parameter.
    """
    auction_code = str(auction_code).strip()
    if len(auction_code) != 6 or not auction_code.isdigit():
        raise ValueError("The auction code must contain exactly six digits.")

    url_parts = urlsplit(st.context.url)
    query = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    query["auction_code"] = auction_code
    return urlunsplit(url_parts._replace(query=urlencode(query), fragment=""))


def join_auction(auction_code: str) -> str:
    """Display a browser link that opens an auction in a new tab.

    Params
    ----------
    auction_code : str
        Six-digit code of the auction to join.

    Returns
    -------
    str
        Public URL displayed by the link button.
    """
    
    auction_link = get_auction_link(auction_code)
    st.link_button(
        "Open auction",
        auction_link,
        icon=":material/open_in_new:",
        type="primary",
        width="stretch",
    )
    return auction_link
