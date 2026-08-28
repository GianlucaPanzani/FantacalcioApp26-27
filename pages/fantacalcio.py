import streamlit as st
import pandas as pd
import lib.ollama_api as llm
from lib.streamlit_api import (
    persistent_session_keys,
    thick_divider,
    highlight_bought_rows,
    sync_filter,
    load_dataset,
    get_role_limits,
    get_role_budget_limits,
    load_env,
    store_env,
    has_full_team,
    generate_pdf_with_bought_players
)


st.set_page_config(
    page_title="Fantacalcio 26-27",
    page_icon="⚽",
    layout="wide",
)

# Load stored persistent values before initializing Session State defaults
load_env(keys=persistent_session_keys, path=".env",)

# Initialize by default values not available in the environment file
st.session_state.setdefault("my_fanta_manager_key", "Me")
st.session_state.setdefault("fanta_managers_key", [st.session_state["my_fanta_manager_key"]])

# Reorder the Fanta Managers with my Fanta Manager as first item
my_fanta_manager = st.session_state["my_fanta_manager_key"]
fanta_managers = st.session_state["fanta_managers_key"]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state["fanta_managers_key"] = fanta_managers

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
    fanta_managers = st.session_state["fanta_managers_key"]
    for fanta_manager in fanta_managers:
        fanta_manager_players_dict.setdefault(fanta_manager, pd.DataFrame())

    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

# Case of data already present in session_state
fanta_manager_players_dict = st.session_state["fanta_manager_players_dict_key"]


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Apply filters currently stored in Streamlit session state."""
    result = df.copy()

    selected_players = st.session_state.get("fanta_player_key", [])
    selected_team = st.session_state.get("fanta_team_key")
    selected_role = st.session_state.get("fanta_role_key")

    if selected_players:
        result = result[result["player"].isin(selected_players)]
    if selected_team:
        result = result[result["team"] == selected_team]
    if selected_role:
        result = result[result["fanta_role"] == selected_role]
    return result


def player_filter(fanta_players: pd.DataFrame) -> pd.DataFrame:

    # Initialize default filter values
    st.session_state.setdefault("fanta_player_key", [])
    st.session_state.setdefault("fanta_team_key", "")
    st.session_state.setdefault("fanta_role_key", "")
    st.session_state.setdefault("selected_fanta_manager_key", "")

    # Apply previous selections before generating widget options.
    options_df = apply_filters(fanta_players)

    names = sorted(options_df["player"].dropna().astype(str).unique())
    teams = sorted(options_df["team"].dropna().astype(str).unique())
    roles = sorted(options_df["fanta_role"].dropna().astype(str).unique())

    # Restore widget values after their options change.
    st.session_state["fanta_player_widget_key"] = [
        player
        for player in st.session_state["fanta_player_key"]
        if player in names
    ]
    st.session_state["fanta_team_widget_key"] = (
        st.session_state["fanta_team_key"]
        if st.session_state["fanta_team_key"] in teams
        else None
    )
    st.session_state["fanta_role_widget_key"] = (
        st.session_state["fanta_role_key"]
        if st.session_state["fanta_role_key"] in roles
        else None
    )
    
    # Create widgets
    cols = st.columns([9,1,9,1,9,1,9,1])
    with cols[0]:
        selected_players = st.multiselect(
            "Search players",
            options=names,
            placeholder="Select one or more players...",
            key="fanta_player_widget_key",
            on_change=sync_filter,
            args=("fanta_player_key", "fanta_player_widget_key"),
        )
    with cols[2]:
        selected_team = st.selectbox(
            "Select team",
            options=teams,
            index=None,
            placeholder="Select a team...",
            key="fanta_team_widget_key",
            on_change=sync_filter,
            args=("fanta_team_key", "fanta_team_widget_key"),
        )
    with cols[4]:
        selected_role = st.selectbox(
            "Select role",
            options=roles,
            index=None,
            placeholder="Select a role...",
            key="fanta_role_widget_key",
            on_change=sync_filter,
            args=("fanta_role_key", "fanta_role_widget_key"),
        )
    with cols[6]:
        selected_fanta_manager = st.selectbox(
            "Select a Fanta Manager",
            options=["Free"] + st.session_state["fanta_managers_key"],
            index=None,
            placeholder="Select a manager...",
            key="fanta_managers_widget_key",
            on_change=sync_filter,
            args=("selected_fanta_manager_key", "fanta_managers_widget_key"),
        )

    st.divider()

    # Apply the values returned by the widgets during the current rerun.
    filtered_df = fanta_players.copy()
    if selected_players:
        filtered_df = filtered_df[filtered_df["player"].isin(selected_players)]
    if selected_team:
        filtered_df = filtered_df[filtered_df["team"] == selected_team]
    if selected_role:
        filtered_df = filtered_df[filtered_df["fanta_role"] == selected_role]
    if selected_fanta_manager == "Free":
        bought_player_ids = set()
        for bought_players in fanta_manager_players_dict.values():
            if "id" in bought_players.columns:
                bought_player_ids.update(bought_players["id"].astype(str))
        filtered_df = filtered_df[~filtered_df["id"].astype(str).isin(bought_player_ids)]
    elif selected_fanta_manager:
        bought_players = fanta_manager_players_dict.get(selected_fanta_manager, pd.DataFrame())
        bought_player_ids = bought_players["id"] if "id" in bought_players.columns else []
        filtered_df = filtered_df[filtered_df["id"].isin(bought_player_ids)]
    
    # Store in session_state
    st.session_state["filtered_players"] = filtered_df
    return filtered_df


def generate_ai_response(fanta_manager_players_dict: dict):
    # Data preparation
    my_players = fanta_manager_players_dict.get(st.session_state["my_fanta_manager_key"], pd.DataFrame()).copy()
    if my_players.empty:
        my_players = pd.DataFrame(columns=["role", "mln"])
    my_players["mln"] = pd.to_numeric(my_players["mln"], errors="coerce").fillna(0).astype(int)
    total_spent = my_players["mln"].sum()
    available_budget = st.session_state["fantacalcio_budget_key"] - total_spent

    role_counts = {
        role: len(my_players.loc[my_players["role"] == role])
        for role in ["P", "D", "C", "A"]
    }
    role_spending = {
        role: my_players.loc[my_players["role"] == role, "mln"].sum()
        for role in ["P", "D", "C", "A"]
    }
    role_limits_dict = get_role_limits()
    role_budget_limits_dict = get_role_budget_limits()

    # Create the prompt for the LLM
    prompt = f"""
    You are an expert in Serie A Fantacalcio.

    Analyze this player:
    {filtered_players.iloc[0].to_dict()}

    My current auction situation:
    - Available budget: {available_budget} mln
    - Goalkeepers: {role_counts["P"]}/{role_limits_dict["P"]} players, {role_spending["P"]}/{role_budget_limits_dict["P"]} mln spent
    - Defenders: {role_counts["D"]}/{role_limits_dict["D"]} players, {role_spending["D"]}/{role_budget_limits_dict["D"]} mln spent
    - Midfielders: {role_counts["C"]}/{role_limits_dict["C"]} players, {role_spending["C"]}/{role_budget_limits_dict["C"]} mln spent
    - Attackers: {role_counts["A"]}/{role_limits_dict["A"]} players, {role_spending["A"]}/{role_budget_limits_dict["A"]} mln spent

    Evaluate the player according to his Fantacalcio role:

    - For goalkeepers, consider starting status, saves, clean-sheet potential and penalty saves.
    - For defenders, consider starting status, defensive reliability, attacking contribution and cards.
    - For midfielders, consider goals, assists, set pieces and tactical role.
    - For attackers, consider starting status, goals, penalties, competition and injury risk.

    Consider his likely playing time, technical characteristics, team context,
    bonus potential, reliability and the needs of my current squad.

    Use only the supplied data and facts you are confident about.
    Do not invent injuries, transfers or starting status. Clearly mention uncertainty
    when current information is unavailable.

    Answer in Italian, using at most 160 words and this structure:

    **Profilo:** brief description of his real playing role and likely usage.

    **Punti a favore**
    - Two or three concise points.

    **Rischi**
    - One or two concise points.

    **Verdetto:** state whether you would buy him and suggest a reasonable maximum bid,
    considering my available budget, remaining role budget and remaining role slots.

    **Voto Fantacalcio:** X/10.
    """

    with st.spinner("Ollama AI is working..."):
        response = llm.query_ollama(
            prompt=prompt,
            content="Follow the user's instructions carefully. Use the supplied data, \
                avoid unsupported claims and respect the requested output format.",
        )

    st.markdown(response)
    return


def create_editor_dataframe(filtered_players: pd.DataFrame, fanta_manager_players_dict: dict):

    # Create the players dataframe to be shown
    bought_players_by_id = {}
    for fanta_manager, bought_players in fanta_manager_players_dict.items():
        if not isinstance(bought_players, pd.DataFrame):
            continue
        for _, bought_player in bought_players.iterrows():
            bought_player_data = bought_player.to_dict()
            bought_player_data["manager"] = fanta_manager
            bought_players_by_id[str(bought_player["id"])] = bought_player_data

    players_editor_df = filtered_players.copy()
    bought_values = players_editor_df["id"].map(lambda player_id: bought_players_by_id.get(str(player_id), {}).get("manager"))
    bought_values = bought_values.fillna("").astype(str)
    mln_values = players_editor_df["id"].map(lambda player_id: bought_players_by_id.get(str(player_id), {}).get("mln", 0))
    mln_values = pd.to_numeric(mln_values, errors="coerce").fillna(0).astype(int)
    players_editor_df.insert(loc=0, column="bought", value=bought_values)
    players_editor_df.insert(loc=1, column="mln", value=mln_values)

    # Use a different widget key when the visible players change.
    fanta_managers = st.session_state["fanta_managers_key"]
    visible_player_ids = tuple(players_editor_df["id"].astype(str).tolist())
    editor_state = (visible_player_ids, tuple(fanta_managers))
    editor_key = f"purchase_editor_{abs(hash(editor_state))}_key"

    # Apply pending manager selections before styling the rows
    editor_changes = st.session_state.get(editor_key, {}).get("edited_rows", {})
    for row_position, changes in editor_changes.items():
        if "bought" in changes:
            selected_manager = changes["bought"]
            selected_manager = "" if pd.isna(selected_manager) else str(selected_manager)
            players_editor_df.iloc[int(row_position), players_editor_df.columns.get_loc("bought")] = selected_manager

    # Create the personalization of some columns for the table
    column_config = {
        column: st.column_config.Column(alignment="center")
        for column in players_editor_df.columns
    }
    column_config.update(
        {
            "bought": st.column_config.SelectboxColumn(
                "Bought",
                help="Select the fanta manager who purchased the player.",
                options=[""] + fanta_managers,
                default=""
            ),
            "mln": st.column_config.NumberColumn(
                "Mln",
                help="Fantamilioni spent for this player.",
                min_value=0,
                step=1,
                format="%d",
                alignment="center",
            ),
            "id": st.column_config.NumberColumn("ID", alignment="center"),
            "player": st.column_config.TextColumn("Player", alignment="center"),
            "team": st.column_config.TextColumn("Team", alignment="center"),
            "fanta_role": st.column_config.TextColumn("R", alignment="center"),
        }
    )

    # Create the table
    edited_players = st.data_editor(
        players_editor_df.style.apply(highlight_bought_rows, axis=1, fanta_managers=fanta_managers),
        hide_index=True,
        width="stretch",
        height=450,
        column_order=["bought", "mln", "player", "team", "fanta_role", "Qt.I", "Qt.A", "FVM"],
        disabled=[column for column in players_editor_df.columns if column not in {"bought", "mln"}],
        column_config=column_config,
        key=editor_key,
    )

    # Update purchases for the players currently visible in the editor.
    for _, player_row in edited_players.iterrows():
        selected_manager = player_row["bought"]

        if pd.isna(selected_manager):
            selected_manager = ""
        else:
            selected_manager = str(selected_manager).strip()

        # Case of price to be initialized
        if pd.isna(player_row["mln"]):
            player_row["mln"] = 0

        player_data = {
            "id": player_row["id"],
            "player": player_row["player"],
            "team": player_row["team"],
            "role": player_row["fanta_role"],
            "mantra_role": player_row.get("mantra_role"),
            "manager": selected_manager,
            "mln": int(player_row["mln"])
        }

        # Remove the player from the previous fanta manager
        for fanta_manager, bought_players in fanta_manager_players_dict.items():
            if not bought_players.empty and "id" in bought_players.columns:
                fanta_manager_players_dict[fanta_manager] = bought_players.loc[bought_players["id"] != player_row["id"]].copy()

        # Add the player to the selected fanta manager
        if selected_manager in fanta_managers:
            bought_players = fanta_manager_players_dict.get(selected_manager, pd.DataFrame()).to_dict("records")
            bought_players.append(player_data)
            fanta_manager_players_dict[selected_manager] = pd.DataFrame(bought_players)

    # Store the updated auction state
    st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

    # Store bought players
    bought_players_dataframes = [bought_players for bought_players in fanta_manager_players_dict.values() if not bought_players.empty]
    if bought_players_dataframes:
        bought_players_df = pd.concat(bought_players_dataframes, ignore_index=True)
    else:
        bought_players_df = pd.DataFrame(columns=["id", "player", "team", "role", "mantra_role", "manager", "mln"])
    st.session_state["bought_players_df_key"] = bought_players_df

    return


def create_current_purchases(fanta_manager_players_dict: dict, fanta_manager=None):
    # Create the df
    if fanta_manager is None:
        fanta_manager = st.session_state["my_fanta_manager_key"]
    bought_players_df = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
    if bought_players_df.empty:
        bought_players_df = pd.DataFrame(columns=["player", "team", "role", "mantra_role", "manager", "mln"])
    bought_players_df["mln"] = pd.to_numeric(bought_players_df["mln"], errors="coerce").fillna(0).astype(int)

    # Compute some budget metric
    starting_budget = st.session_state.get("fantacalcio_budget_key", 500)
    tot_spent = bought_players_df["mln"].sum()
    available_budget = starting_budget - tot_spent

    # Create columns
    budget_col, _, p_col, _, d_col, _, c_col, _, a_col = st.columns([10,1,9,1,9,1,9,1,9])

    role_limits_dict = get_role_limits()
    role_columns_dict = {
        "P": (p_col, "Goalkeepers", role_limits_dict["P"]),
        "D": (d_col, "Defenders", role_limits_dict["D"]),
        "C": (c_col, "Midfielders", role_limits_dict["C"]),
        "A": (a_col, "Attackers", role_limits_dict["A"]),
    }

    # Create the bought of the budget
    with budget_col:
        st.html(
            """
            <style>
            [class*="budget-metric"] [data-testid="stMetricLabel"] p {
                font-size: 1.25rem;
            }
            </style>
            """
        )
        with st.container(key=f"{fanta_manager}-budget-metric"):
            st.metric(
                label=f"Available cash for :blue[**{fanta_manager}**]",
                value=f":green[+{available_budget}] mln",
                delta=f"-{tot_spent} mln" if tot_spent > 0 else "",
                delta_color="blue" if tot_spent > 0 else "gray",
                icon="💰",
                border=True
            )

        if available_budget < 0:
            st.error("Budget exceeded")

    # Create the columns for the bought players
    role_budget_limits_dict = get_role_budget_limits()
    for role, (col, role_label, role_limit) in role_columns_dict.items():
        role_budget_limit = role_budget_limits_dict[role]

        # Players bought with the role "role"
        bought_players_role = bought_players_df.loc[bought_players_df["role"] == role]
        tot_spent_for_role = bought_players_role['mln'].sum()
        st.session_state[f"{fanta_manager}_num_of_bought_{role}_key"] = len(bought_players_role)
        st.session_state[f"{fanta_manager}_{role}_budget_limit_exceeded"] = tot_spent_for_role > role_limit

        with col:
            with st.container(border=True, width="stretch", height="stretch"):

                delta_str = \
                    f"-{tot_spent_for_role} mln" if tot_spent_for_role > 0 and tot_spent_for_role < role_budget_limit \
                    else f"-{tot_spent_for_role} mln [exceeded {role_budget_limit}]" if tot_spent_for_role > role_budget_limit \
                    else "0 mln"
                delta_color_str = "grey" if tot_spent_for_role == 0 else "red" if tot_spent_for_role > role_budget_limit else "blue"

                st.metric(
                    label=f"{role_label} ({role})",
                    value=f"{len(bought_players_role)}/{role_limit}",
                    delta=delta_str,
                    delta_color=delta_color_str,
                )

                st.divider()

                if len(bought_players_role) > role_limit:
                    st.session_state[f"{fanta_manager}_{role}_limit_exceeded"] = True
                    st.error("Role limit exceeded: remove the last purchase.")
                else:
                    st.session_state[f"{fanta_manager}_{role}_limit_exceeded"] = False

                # Case of no player bought for this role
                if bought_players_role.empty:
                    st.caption("No players purchased")
                    continue
                
                # List the bought players
                for _, player_row in bought_players_role.iterrows():
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.session_state[f"{fanta_manager}_{role}_limit_exceeded"]:
                            st.markdown(f"- :red[**{player_row['player']}**]")
                        else:
                            st.markdown(f"- **{player_row['player']}**")
                    with col2:
                        st.markdown(
                            f":small[:grey[{player_row['mln']} mln]]  \n"
                            f":small[:grey[{player_row['team']}]]",
                            text_alignment="right"
                        )

    return


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

st.title("⚽ Fantacalcio 26-27 - Create your own team")

thick_divider()

# Filters + players table
st.header("Fanta List")
st.caption(
    "Search or reduce the players in the table using the following filters.\n"
    "Select the Fanta Manager on the first column if someone has bought a player and set the millions spent to update the teams."
)
fanta_players = load_dataset("data/filtered_history_players.csv", filter_by_current_year=True)
filtered_players = player_filter(fanta_players)
create_editor_dataframe(filtered_players, fanta_manager_players_dict)

# Case of AI enabled
if st.session_state["ai_enabled_key"] and filtered_players.shape[0] == 1:
    generate_ai_response(fanta_manager_players_dict)

thick_divider()

# Teams of the Fanta Managers
st.header("Teams & Billing")
st.divider()
for fanta_manager in st.session_state["fanta_managers_key"]:
    create_current_purchases(fanta_manager_players_dict, fanta_manager)
    st.divider()

# Store only persistent Session State values
store_env(
    data_dict={key: st.session_state[key] for key in persistent_session_keys if key in st.session_state},
    path=".env",
)

# Case of pdf generation
auction_completed = True
for fanta_manager in fanta_manager_players_dict:
    if not has_full_team(fanta_manager):
        auction_completed = False
if auction_completed:
    with st.spinner("Building the teams file..."):
        generate_pdf_with_bought_players()
    
