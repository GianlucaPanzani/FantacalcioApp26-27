import json
import numpy as np
import pandas as pd
import requests

from lib.data_handler import get_candidates_by_season


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
    raise TypeError(
        f"Object of type {type(value).__name__} is not JSON serializable"
    )


def build_candidates_request(fanta_row, candidates):
    """Build a JSON-compatible request for row-level entity matching.

    Params
    ----------
    fanta_row : pandas.Series
        Fantacalcio player to match.
    candidates : pandas.DataFrame
        Historical player candidates with their matching metadata.

    Returns
    -------
    dict
        Player data and candidate records ready for JSON serialization.
    """
    candidate_objects = []
    for _, row in candidates.iterrows():
        candidate_objects.append({
            "candidate_id": int(row["candidate_id"]),
            "name": row.get("player"),
            "season": row.get("season"),
            "team": row.get("team"),
            "competition": row.get("competition"),
            "nationality": row.get("nationality"),
            "position": row.get("position"),
            "age": row.get("age"),
            "birth_year": row.get("birth_year"),
        })
    return {
        "fanta_player": {
            "name": fanta_row.get("Nome"),
            "team": fanta_row.get("Squadra"),
            "role": fanta_row.get("RM"),
        },
        "candidates": candidate_objects,
    }

def query_ollama(prompt, model="qwen3:4b", content="Football players for Fantacalcio", format=None):
    """Send a prompt to a locally running Ollama model.

    Params
    ----------
    prompt : str
        User prompt sent to the model.
    model : str
        Name of the locally installed Ollama model.
    content : str
        System instruction that defines the model task.
    format : dict or None
        Optional JSON schema required for the response.

    Returns
    -------
    str
        Content of the model response.
    """
    json_dict = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": content,
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0,
        },
    }

    if format is not None:
        json_dict["format"] = format

    response = requests.post(
        url="http://localhost:11434/api/chat",
        json=json_dict,
        timeout=300,
    )

    response.raise_for_status()
    return response.json()["message"]["content"]


def get_filtered_history_with_llm_matches(players, history_players, prompt):
    """Match Fantacalcio players to historical records with a local LLM.

    Params
    ----------
    players : pandas.DataFrame
        Fantacalcio players that need historical matches.
    history_players : pandas.DataFrame
        Historical player records used to build match candidates.
    prompt : str
        Prompt template containing a ``{request_data}`` placeholder.

    Returns
    -------
    tuple of pandas.DataFrame
        Matched historical rows and a report of players that could not be matched.
    """
    format_dict = {
        "type": "object",
        "properties": {
            "matched_candidate_ids": {
                "type": "array",
                "items": {
                    "type": "integer"
                }
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "reason": {
                "type": "string"
            }
        },
        "required": [
            "matched_candidate_ids",
            "confidence",
            "reason"
        ],
        "additionalProperties": False
    }

    llm_matched_rows = []
    failed_matches = []
    for _, fanta_row in players.iterrows():

        # Get the top 3 candidates for the current fanta_player
        candidates = get_candidates_by_season(
            fanta_name=fanta_row["Nome"],
            history_df=history_players,
            top_k=5,
        )

        # Build the request data for the LLM
        request_data = build_candidates_request(
            fanta_row,
            candidates,
        )

        # Query the LLM to find the matches
        try:
            response = query_ollama(
                prompt=prompt.replace(
                    "{request_data}",
                    json.dumps(
                        request_data,
                        ensure_ascii=False,
                        indent=2,
                        default=json_converter,
                    )
                ),
                content="You perform football player entity matching. Follow the requested output format exactly.",
                format=format_dict
            )
            if isinstance(response, str):
                response = json.loads(response)
        except Exception as e:
            failed_matches.append({
                "fanta_player": fanta_row["Nome"],
                "reason": str(e),
                "confidence": None,
            })
            continue
        
        # Save the matched candidates IDs
        matched_ids = response.get("matched_candidate_ids", [])
        if not matched_ids:
            failed_matches.append({
                "fanta_player": fanta_row["Nome"],
                "reason": response.get("reason"),
                "confidence": response.get("confidence"),
            })
            continue

        # Select every historical row approved by the LLM
        selected_rows = candidates[candidates["candidate_id"].isin(matched_ids)].copy()

        # Add information about the Fantacalcio match.
        selected_rows["fanta_player"] = fanta_row["Nome"]
        selected_rows["llm_confidence"] = response.get("confidence")
        selected_rows["llm_reason"] = response.get("reason")

        llm_matched_rows.append(selected_rows)

    # Concatenate all the matched rows in a single DataFrame
    matches = pd.concat(llm_matched_rows, ignore_index=True)
    return matches, pd.DataFrame(failed_matches)
