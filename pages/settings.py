import streamlit as st
import pandas as pd


import lib.ollama_api as llm
from lib.streamlit_api import (
    persistent_session_keys,
    thick_divider,
    get_fanta_manager_players_dict,
    sync_filter,
    load_dataset,
    load_env,
    store_env
)


st.set_page_config(
    page_title="Settings",
    page_icon="⚙️",
    layout="wide",
)


st.title("⚙️ Settings")
st.caption("Customize your Fantacalcio's parameters.")

load_env(keys=persistent_session_keys, path=".env")

st.session_state.setdefault("my_fanta_manager_key", "Me")
st.session_state.setdefault("fanta_managers_key", [st.session_state["my_fanta_manager_key"]])

my_fanta_manager = st.session_state["my_fanta_manager_key"]

# Reorder the Fanta Managers with my Fanta Manager as first item
fanta_managers = st.session_state["fanta_managers_key"]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state["fanta_managers_key"] = fanta_managers

fanta_manager_players_dict = get_fanta_manager_players_dict()


# Fanta Managers settings
with st.container(border=True):

    cols = st.columns([10,2,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Fanta Managers**")

    with cols[2]:

        new_my_fanta_manager = st.text_input(
            label="Your Fanta Manager name",
            placeholder=st.session_state["my_fanta_manager_key"],
            key="my_fanta_manager_widget_key",
        ).strip()

        managers_list = [manager.lower() for manager in fanta_managers]
        update_warning = None
        if not new_my_fanta_manager:
            update_warning = "Enter a fanta manager name"
        elif new_my_fanta_manager.lower() in managers_list:
            update_warning = "Fanta manager already present"

        update_fanta_manager_button = st.button("Update", width="stretch")
        if update_fanta_manager_button and update_warning is None:
            current_fanta_manager = st.session_state["my_fanta_manager_key"]

            bought_players = fanta_manager_players_dict.pop(current_fanta_manager, pd.DataFrame())
            if not bought_players.empty:
                bought_players["manager"] = new_my_fanta_manager

            fanta_manager_players_dict[new_my_fanta_manager] = bought_players
            fanta_managers.remove(current_fanta_manager)
            fanta_managers.insert(0, new_my_fanta_manager)
            st.session_state["my_fanta_manager_key"] = new_my_fanta_manager
            st.session_state["fanta_managers_key"] = fanta_managers
            st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[4]:

        new_fanta_manager = st.text_input(
            label="Add a new Fanta Manager",
            placeholder="Enter a name...",
            key="new_fanta_manager_widget_key",
        ).strip()

        managers_list = [manager.lower() for manager in fanta_managers]
        add_warning = None
        if not new_fanta_manager:
            add_warning = "Enter a fanta manager name"
        elif new_fanta_manager.lower() in managers_list:
            add_warning = "Fanta manager already present"

        add_fanta_manager_button = st.button("Add", width="stretch")
        if add_fanta_manager_button and add_warning is None:
            fanta_managers.append(new_fanta_manager)
            fanta_manager_players_dict[new_fanta_manager] = pd.DataFrame()
            st.session_state["fanta_managers_key"] = fanta_managers
            st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[6]:

        selected_fanta_manager = st.selectbox(
            "Select a Fanta Manager to remove",
            options=fanta_managers,
            index=None,
            placeholder="Select a manager...",
            key="remove_fanta_manager_widget_key",
            on_change=sync_filter,
            args=("remove_fanta_manager_key", "remove_fanta_manager_widget_key"),
        )

        remove_warning = None
        if not selected_fanta_manager:
            remove_warning = "Select a fanta manager"
        elif selected_fanta_manager == st.session_state["my_fanta_manager_key"]:
            remove_warning = "You cannot remove your own Fanta Manager"

        remove_fanta_manager_button = st.button("Remove", width="stretch")
        if remove_fanta_manager_button and remove_warning is None:
            fanta_managers.remove(selected_fanta_manager)
            fanta_manager_players_dict.pop(selected_fanta_manager, None)
            st.session_state["fanta_managers_key"] = fanta_managers
            st.session_state["fanta_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[8]:

        manager_badges = " ".join(
            f":green-badge[{manager}]"
            if manager == st.session_state["my_fanta_manager_key"]
            else f":blue-badge[{manager}]"
            for manager in fanta_managers
        )
        st.markdown(
            f":material/groups: **Fanta managers**  \n"
            f"{manager_badges}"
        )

        if update_fanta_manager_button:
            if update_warning:
                st.info(update_warning)
            else:
                st.success("Name updated successfully")
        if add_fanta_manager_button:
            if add_warning:
                st.info(add_warning)
            else:
                st.success("Fanta Manager added successfully")
        if remove_fanta_manager_button:
            if remove_warning:
                st.info(remove_warning)
            else:
                st.success("Fanta Manager removed successfully")

# Auction settings
with st.container(border=True):

    cols = st.columns([10,2,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Players per role**")

    with cols[2]:
        goalkeepers_limit = st.number_input(
            "Number of Goalkeepers (P)",
            min_value=0,
            value=3,
            step=1,
            key="fantacalcio_goalkeepers_limit_key",
        )
    with cols[4]:
        defenders_limit = st.number_input(
            "Number of Defenders (D)",
            min_value=0,
            value=8,
            step=1,
            key="fantacalcio_defenders_limit_key",
        )
    with cols[6]:
        midfielders_limit = st.number_input(
            "Number of Midfielders (C)",
            min_value=0,
            value=8,
            step=1,
            key="fantacalcio_midfielders_limit_key",
        )
    with cols[8]:
        attackers_limit = st.number_input(
            "Number of Attackers (A)",
            min_value=0,
            value=6,
            step=1,
            key="fantacalcio_attackers_limit_key",
        )

# Budget limits settings
with st.container(border=True):

    cols = st.columns([10,2,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Budget limits per role**")

    with cols[2]:
        budget = st.number_input(
            "Available budget (mln)",
            min_value=0,
            value=500,
            step=50,
            key="fantacalcio_budget_key",
        )

    cols = st.columns([10,2,8,1,8,1,8,1,8])

    with cols[2]:
        goalkeepers_budget_limit = st.number_input(
            "Budget for Goalkeepers (P)",
            min_value=0,
            max_value=500,
            value=50,
            step=5,
            key="fantacalcio_goalkeepers_budget_limit_key",
        )
    with cols[4]:
        defenders_budget_limit = st.number_input(
            "Budget for Defenders (D)",
            min_value=0,
            max_value=500,
            value=100,
            step=5,
            key="fantacalcio_defenders_budget_limit_key",
        )
    with cols[6]:
        midfielders_budget_limit = st.number_input(
            "Budget for Midfielders (C)",
            min_value=0,
            max_value=500,
            value=200,
            step=5,
            key="fantacalcio_midfielders_budget_limit_key",
        )
    with cols[8]:
        attackers_budget_limit = st.number_input(
            "Budget for Attackers (A)",
            min_value=0,
            max_value=500,
            value=150,
            step=5,
            key="fantacalcio_attackers_budget_limit_key",
        )
    
    cols = st.columns([10,3,36,1])
    
    with cols[2]:
        budget_limit_sum = goalkeepers_budget_limit + defenders_budget_limit + midfielders_budget_limit + attackers_budget_limit
        if "fantacalcio_budget_key" in st.session_state and budget_limit_sum > st.session_state["fantacalcio_budget_key"]:
            st.error(f"Budget limit exceeded: {budget_limit_sum}/{st.session_state['fantacalcio_budget_key']}.")
        if "fantacalcio_budget_key" in st.session_state and budget_limit_sum < st.session_state["fantacalcio_budget_key"]:
            st.info(f"You can still use {int(st.session_state['fantacalcio_budget_key']) - budget_limit_sum} mln.")

# AI settings
with st.container(border=True):

    cols = st.columns([10,2,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **AI settings**")

    with cols[2]:
        ai_enabled = st.toggle(
            "Activate AI to help you",
            value=False,
            key="ai_enabled_key",
        )


# Synchronize bought players after adding, renaming or removing a manager
bought_players_dataframes = [
    bought_players
    for bought_players in fanta_manager_players_dict.values()
    if not bought_players.empty
]
if bought_players_dataframes:
    bought_players_df = pd.concat(bought_players_dataframes, ignore_index=True)
else:
    bought_players_df = pd.DataFrame(columns=["id", "player", "team", "role", "mantra_role", "manager", "mln"])
st.session_state["bought_players_df_key"] = bought_players_df

# Store only persistent Session State values
store_env(
    data_dict={key: st.session_state[key] for key in persistent_session_keys if key in st.session_state},
    path=".env"
)
