import time
from datetime import datetime, timezone
from pathlib import Path
import unicodedata
import pandas as pd
import requests


API_KEY = "123"
BASE_URL = f"https://www.thesportsdb.com/api/v1/json/{API_KEY}"

# Official free limit = 30/min.
# Keep a small safety margin.
REQUESTS_PER_MINUTE = 28
MIN_INTERVAL = 60 / REQUESTS_PER_MINUTE

REQUEST_TIMEOUT = 20
MAX_RETRIES = 3


def normalize_name_for_img_scraping(name: str) -> str:
    """Normalize a player name before comparing image-search results."""
    name = unicodedata.normalize("NFKD", str(name))
    name = "".join(char for char in name if not unicodedata.combining(char))
    return " ".join(name.lower().strip().split())


def is_creative_commons(value) -> bool:
    """Return whether TheSportsDB marks a player's artwork as Creative Commons."""
    if value is None:
        return False

    value = str(value).strip().lower()

    return value in {"yes", "true", "1", "y"}


def request_player(player_name: str, session: requests.Session) -> dict | None:
    """Request one player from TheSportsDB with retry and rate-limit handling.

    Params
    ----------
    player_name : str
        Player name sent to the search endpoint.
    session : requests.Session
        Reusable HTTP session.

    Returns
    -------
    dict or None
        First API player result, or ``None`` after an empty or failed search.
    """

    url = f"{BASE_URL}/searchplayers.php"

    for attempt in range(MAX_RETRIES):

        try:
            response = session.get(
                url,
                params={"p": player_name},
                timeout=REQUEST_TIMEOUT
            )

            # Rate limit reached
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 65))
                print(f"[RATE LIMIT] Waiting {retry_after}s...")
                time.sleep(retry_after)
                continue

            response.raise_for_status()
            data = response.json()

            # Be tolerant to possible response-key variations
            players = (
                data.get("player")
                or data.get("players")
            )

            if not players:
                return None

            # Free search currently returns at most one result
            return players[0]

        except requests.RequestException as error:
            print(f"[ERROR] {player_name}: {error}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(5 * (attempt + 1))

    return None


def create_player_row(searched_name: str, api_player: dict | None) -> dict:
    """Add provenance and artwork metadata to a player API result.

    Params
    ----------
    searched_name : str
        Original player name used for the API query.
    api_player : dict or None
        Player object returned by TheSportsDB.

    Returns
    -------
    dict
        Normalized output row, including metadata for unsuccessful searches.
    """

    timestamp = datetime.now(timezone.utc).isoformat()

    if api_player is None:
        return {
            "query_name": searched_name,
            "found": False,
            "name_match": False,
            "source": "TheSportsDB",
            "retrieved_at": timestamp
        }

    row = dict(api_player)

    api_name = row.get("strPlayer")
    cc_value = row.get("strCreativeCommons")

    # Add our own provenance / validation metadata
    row["query_name"] = searched_name
    row["found"] = True
    row["name_match"] = (
        normalize_name_for_img_scraping(searched_name)
        == normalize_name_for_img_scraping(api_name)
    )
    row["cc_artwork"] = is_creative_commons(cc_value)
    row["artwork_usage_status"] = (
        "CC_TAGGED"
        if row["cc_artwork"]
        else "REVIEW_REQUIRED"
    )
    row["source"] = "TheSportsDB"
    row["source_player_url"] = (
        f"https://www.thesportsdb.com/player/{row.get('idPlayer')}"
        if row.get("idPlayer")
        else None
    )
    row["retrieved_at"] = timestamp

    return row


def fetch_players(player_names: list[str], output_file: Path) -> pd.DataFrame:
    """Fetch player images and save a progressive CSV checkpoint.

    Params
    ----------
    player_names : list of str
        Player names to search sequentially.
    output_file : pathlib.Path
        CSV path updated after every completed request.

    Returns
    -------
    pandas.DataFrame
        API results and provenance metadata for every requested player.
    """

    output_file.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()

    rows = []
    last_request_time = 0.0
    n_players = len(player_names)
    for i, player_name in enumerate(player_names, start=1):

        # Rate limiting (because of web site limitation of #requests per time)
        current_request_time = time.monotonic()
        elapsed = current_request_time - last_request_time
        sleep_time = MIN_INTERVAL - elapsed
        slept = False
        if sleep_time > 0:
            time.sleep(sleep_time)
            slept = True

        print(f"[{i}/{n_players}] Searching: {player_name}: ", end="")

        api_player = request_player(player_name, session)
        
        last_request_time = time.monotonic()

        row = create_player_row(
            searched_name=player_name,
            api_player=api_player
        )
        rows.append(row)

        if row["found"]:
            print(f" found in {last_request_time - current_request_time}{f' [SLEEP={slept}]' if slept else ''}.")
        else:
            print("not found.")

        # Progressive checkpoint
        df = pd.DataFrame(rows)
        df.to_csv(output_file, index=False)

    session.close()

    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False)

    print(f"\nSaved {len(df)} players to: {output_file}")
    return df


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

players = pd.read_csv("../data/csv/notebooks_generated/Listone_Fantacalcio_Stagione_2026_27.csv")
fetch_players(
    player_names=players["Nome"].to_list(),
    output_file=Path("../data/csv/online_sources/players_thesportsdb.csv")
)
