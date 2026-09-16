import streamlit as st
import pandas as pd
from lib.xgboost_predictor import (
    features_to_predict_list
)
from lib.utils import (
    interest_colors_dict,
    highlight_interest,
    get_current_year,
    get_circular_role_icon,
    get_color_per_role,
    get_background_img_path
)
from lib.streamlit_api import (
    thick_divider,
    bottom_caption,
    set_page_background,
    set_dark_background,
    highlight_bought_rows,
    sync_filter,
    load_dataset,
    load_models,
    print_models_predictions,
    get_roles_dict,
    get_role_limits,
    get_role_budget_limits,
    get_role_limits,
    set_text_size,
    load_env,
    load_models,
    store_env,
    restore_bought_players,
    has_full_team,
    save_bought_players,
    get_icon
)


st.set_page_config(
    page_title=f"{get_icon("auction")} Auction 26-27",
    layout="wide",
)

page_name = "fantacalcio"

img_path = get_background_img_path(page_name)
set_page_background(img_path)
set_dark_background()

columns_to_filter_list = [
    "player",
    "team",
    "fanta_role",
]

compare_op_for_columns_to_filter_dict = {
    "player": None,
    "team": "eq",
    "fanta_role": "eq",
}

fanta_manager_split_value_key = f"{page_name}_fanta_managers_split_value"
fanta_manager_split_value_widget_key = f"{page_name}_fanta_managers_split_value_widget"
enable_bought_players_stats_key = f"{page_name}_bought_players_stats_key"
enable_player_preferences_key = f"{page_name}_enable_player_preferences_key"
reset_managers_widget_key = f"{page_name}_reset_managers_widget_key"
reset_boughts_button_key = f"{page_name}_reset_boughts_button_key"
reset_bought_message_key = f"{page_name}_reset_boughts_message_key"
show_ai_predictions_key = f"{page_name}_show_ai_predictions_key"
show_ai_explainations_key = f"{page_name}_show_ai_explainations_key"
show_ai_plots_key = f"{page_name}_show_ai_plots_key"
hide_other_fantamanagers_key = f"{page_name}_hide_other_fantamanagers_key"

bought_player_columns = ["id", "player", "team", "role", "mantra_role", "manager", "mln"]


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================



# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

# Block 1: Load participant settings and stop until another manager has joined.
loaded_env_values = load_env(path=".env")

# Track the persistent keys already stored for this page.
fantacalcio_keys_set = {
    key
    for key in loaded_env_values
    if key.startswith(f"{page_name}_")
}

# Initialize missing manager and auction settings.
settings_my_manager_key = "settings_my_manager_key"
fantacalcio_keys_set.add(settings_my_manager_key)
st.session_state.setdefault(settings_my_manager_key, "Me")
settings_managers_key = "settings_managers_key"
fantacalcio_keys_set.add(settings_managers_key)
st.session_state.setdefault(settings_managers_key, [st.session_state[settings_my_manager_key]])
settings_budget_key = "settings_budget_key"
fantacalcio_keys_set.add(settings_budget_key)
st.session_state.setdefault(settings_budget_key, 500)
settings_ai_enabled_key = "settings_ai_enabled_key"
fantacalcio_keys_set.add(settings_ai_enabled_key)
st.session_state.setdefault(settings_ai_enabled_key, False)

# Show the current manager first and check for at least one other participant.
my_fanta_manager = st.session_state[settings_my_manager_key]
fanta_managers = st.session_state[settings_managers_key]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state[settings_managers_key] = fanta_managers

'''
try:
    participant = register_to_auction(
        auth_issuer=st.user.iss,
        auth_subject=st.user.sub,
        username=st.session_state[f"{page_name}_username_key"],
        invite_code=st.session_state[f"{page_name}_invite_code_key"],
        team_name=st.session_state[f"{page_name}_team_name_key"],
    )
except ValueError as error:
    st.error(error)
    st.stop()
except sqlite3.IntegrityError:
    st.warning("This username or team name is already in use.")
    st.stop()
'''


if not any(manager != my_fanta_manager for manager in fanta_managers):
    st.info("Add at least one other Fanta Manager in Settings before accessing the auction.")
    st.stop()

# Block 2: Load the auction data and display the complete auction interface.
models_packages_dict = load_models(target_features=features_to_predict_list)
feature_explanations = load_dataset("data/csv/models_generated/features_explainability.csv")

# Restore purchased players when their session data has not been initialized.
if f"{page_name}_manager_players_dict_key" not in st.session_state:
    restore_bought_players(
        bought_players_df_key=f"{page_name}_bought_players_df_key",
        settings_managers_key=settings_managers_key,
        fanta_manager_players_dict_key=f"{page_name}_manager_players_dict_key"
    )
fanta_manager_players_dict = st.session_state[f"{page_name}_manager_players_dict_key"]

# Load the optional preferences stored by the Players Selection page
player_preferences = None
if st.session_state[enable_player_preferences_key]:
    selection_players_path = st.session_state.get(
        "selection_selected_players_csv_path_key",
        "data/csv/pages/selection/selection_selected_players.csv",
    )
    player_preferences = load_player_preferences(selection_players_path)

# Load player history for statistics and model explanations.
history_players = load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv")

# Load the current-season player pool for the auction table.
fanta_players = load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv", filter_by_current_year=True)

# Render the sidebar controls for layout, AI views, and team resets.
with st.sidebar:

    st.markdown("### General settings")
    general_filters()
    st.divider()

    st.markdown("### AI settings")
    filtered_players = checkbox_filters(fanta_players)
    st.divider()

    st.markdown("### Reset teams")
    reset_teams_filters(fanta_managers)

# Display the auction title and describe the available tools.
year = get_current_year()
st.title(f"{get_icon('auction')} Auction {year}-{year+1}")
st.caption(
    "Run the auction by filtering players, reviewing saved preferences and AI predictions, assigning purchases "
    "and prices, monitoring budgets and role limits, and exporting the completed teams to PDF."
)

st.space(15)

# Offer a full-width start request before the player table; permissions will follow.
auction_start_requested_key = "auction_start_requested_key"
st.session_state.setdefault(auction_start_requested_key, False)
st.button(
    "Start auction",
    type="primary",
    icon=":material/play_arrow:",
    width="stretch",
    key="auction_request_start_button_key",
    disabled=st.session_state[auction_start_requested_key],
    on_click=request_auction_start,
)
if st.session_state[auction_start_requested_key]:
    st.success("Auction start requested.")

# Render player filters, the editable dataset, and the optional interest legend.
if not st.session_state[enable_player_preferences_key]:
    cols = st.columns([7,1,52])
    with cols[0]:
        with st.container(border=True, key=f"dark-card-{page_name}_plyer_filters_key"):
            st.markdown("#### Filters")
            filtered_players = player_filters(filtered_players)
    with cols[2]:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
else:
    cols = st.columns([11,1,40,1,7])
    with cols[0]:
        with st.container(border=True, key=f"dark-card-{page_name}_plyer_filters_key"):
            st.markdown("#### Filters")
            filtered_players = player_filters(filtered_players)
    with cols[2]:
        create_editor_dataframe(filtered_players, fanta_manager_players_dict, player_preferences)
    with cols[4]:
        if st.session_state[enable_player_preferences_key]:
            with st.container(border=True, height="stretch", width="content", key=f"dark-card-interest_container_key"):
                st.markdown("**Interest meanings**:")
                for interest, color in interest_colors_dict.items():
                    st.markdown(f':color[●]{{foreground="{color}"}} :small[{interest}]')

# Show AI predictions only when enabled and exactly one player is selected.
if st.session_state[show_ai_predictions_key] and filtered_players.shape[0] == 1:
    st.divider()

    selected_player = filtered_players.iloc[0]
    history_of_the_player = history_players[
        history_players["player"].eq(selected_player["player"])
        & history_players["season"].lt(selected_player["season"])
    ]

    print_models_predictions(
        models_packages_dict=models_packages_dict,
        history_players=history_players,
        history_of_the_player=history_of_the_player,
        player_row=filtered_players.iloc[0],
        top_k=4,
        worst_k=2,
        explainability_enabled=st.session_state[show_ai_explainations_key],
        plots_enebled=st.session_state[show_ai_plots_key],
    )

# Offer team downloads when all managers have completed their squads.
auction_completed = True
for fanta_manager in fanta_manager_players_dict:
    if not has_full_team(fanta_manager):
        auction_completed = False
if auction_completed:
    st.divider()
    download_col, managers_col = st.columns([6,20])
    with download_col:
        st.subheader("Download teams")
        save_bought_players(page_name)
else:
    managers_col = st.columns(1)[0]

# Display manager squads in the selected horizontal or vertical layout.
with managers_col:
    split_value = st.session_state[fanta_manager_split_value_key]
    ordered_manager_items = [
        (my_fanta_manager, fanta_manager_players_dict.get(my_fanta_manager, pd.DataFrame())),
    ] + [
        (fanta_manager, players)
        for fanta_manager, players in fanta_manager_players_dict.items()
        if fanta_manager != my_fanta_manager
    ]
    fanta_manager_players_dict_splitted: list[dict] = [
        dict(ordered_manager_items[i:i + split_value])
        for i in range(0, len(ordered_manager_items), split_value)
    ]
    for fanta_manager_players_chunk in fanta_manager_players_dict_splitted:
        if split_value > 1:
            create_vertical_teams(fanta_manager_players_chunk, split_value)
        elif split_value == 1:
            create_horizontal_teams(fanta_manager_players_chunk)

# Persist the existing page settings and purchases using the current storage format.
fantacalcio_bought_players_df_key = f"{page_name}_bought_players_df_key"
fantacalcio_keys_set.add(fantacalcio_bought_players_df_key)
fantacalcio_keys_list = list(fantacalcio_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in fantacalcio_keys_list if key in st.session_state},
    path=".env",
)

# Render the page footer.
bottom_caption()
