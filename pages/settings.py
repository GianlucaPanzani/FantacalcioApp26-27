import streamlit as st
import pandas as pd


import lib.ollama_api as llm
from lib.streamlit_api import (
    thick_divider,
    toast_css_format,
    get_user_view_of_column,
    get_fanta_manager_players_dict,
    get_roles_list,
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

page_name = "settings"


st.title("⚙️ Settings")
st.caption("Customize your Fantacalcio's parameters.")

loaded_env_values = load_env(path=".env")
settings_keys_set = set(loaded_env_values)

my_manager_key = f"{page_name}_my_manager_key"
settings_keys_set.add(my_manager_key)
st.session_state.setdefault(my_manager_key, "Me")

managers_key = f"{page_name}_managers_key"
settings_keys_set.add(managers_key)
st.session_state.setdefault(managers_key, [st.session_state[my_manager_key]])

my_fanta_manager = st.session_state[f"{page_name}_my_manager_key"]

# Reorder the Fanta Managers with my Fanta Manager as first item
fanta_managers = st.session_state[f"{page_name}_managers_key"]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state[f"{page_name}_managers_key"] = fanta_managers

# Getting data
fanta_manager_players_dict = get_fanta_manager_players_dict()
roles_list = get_roles_list()
roles_with_aka_list = get_roles_list(enable_aka=True)
history_players = load_dataset("data/filtered_history_players.csv")


# Fanta Managers settings
with st.container(border=True):

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Fanta Managers**")

    with cols[2]:

        new_my_fanta_manager = st.text_input(
            label="Your Fanta Manager name",
            placeholder=st.session_state[f"{page_name}_my_manager_key"],
            key=f"{page_name}_my_manager_widget_key",
        ).strip()

        managers_list = [manager.lower() for manager in fanta_managers]
        update_warning = None
        if not new_my_fanta_manager:
            update_warning = "Enter a fanta manager name"
        elif new_my_fanta_manager.lower() in managers_list:
            update_warning = "Fanta manager already present"

        update_fanta_manager_button = st.button("Update", width="stretch")
        if update_fanta_manager_button and update_warning is None:
            current_fanta_manager = st.session_state[f"{page_name}_my_manager_key"]

            bought_players = fanta_manager_players_dict.pop(current_fanta_manager, pd.DataFrame())
            if not bought_players.empty:
                bought_players["manager"] = new_my_fanta_manager

            fanta_manager_players_dict[new_my_fanta_manager] = bought_players
            fanta_managers.remove(current_fanta_manager)
            fanta_managers.insert(0, new_my_fanta_manager)
            st.session_state[f"{page_name}_my_manager_key"] = new_my_fanta_manager
            st.session_state[f"{page_name}_managers_key"] = fanta_managers
            st.session_state["fantacalcio_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[4]:

        new_fanta_manager = st.text_input(
            label="Add a new Fanta Manager",
            placeholder="Enter a name...",
            key=f"{page_name}_new_manager_widget_key",
        ).strip()

        managers_list = [manager.lower() for manager in fanta_managers]
        add_warning = None
        if not new_fanta_manager:
            add_warning = "Enter a fanta manager name"
        elif new_fanta_manager.lower() in managers_list:
            add_warning = "Fanta manager already present"

        add_fanta_manager_button = st.button(
            "Add",
            width="stretch",
            key=f"{page_name}_add_manager_button_key"
        )
        if add_fanta_manager_button and add_warning is None:
            fanta_managers.append(new_fanta_manager)
            fanta_manager_players_dict[new_fanta_manager] = pd.DataFrame()
            st.session_state[f"{page_name}_managers_key"] = fanta_managers
            st.session_state["fantacalcio_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[6]:

        selected_fanta_manager = st.selectbox(
            "Select a Fanta Manager to remove",
            options=fanta_managers,
            index=None,
            placeholder="Select a manager...",
            key=f"{page_name}_remove_manager_widget_key",
            on_change=sync_filter,
            args=(f"{page_name}_remove_manager_key", f"{page_name}_remove_manager_widget_key"),
        )

        remove_warning = None
        if not selected_fanta_manager:
            remove_warning = "Select a fanta manager"
        elif selected_fanta_manager == st.session_state[f"{page_name}_my_manager_key"]:
            remove_warning = "You cannot remove your own Fanta Manager"

        remove_fanta_manager_button = st.button(
            "Remove",
            width="stretch",
            key=f"{page_name}_rm_manager_button_key"
        )
        if remove_fanta_manager_button and remove_warning is None:
            fanta_managers.remove(selected_fanta_manager)
            fanta_manager_players_dict.pop(selected_fanta_manager, None)
            st.session_state[f"{page_name}_managers_key"] = fanta_managers
            st.session_state["fantacalcio_manager_players_dict_key"] = fanta_manager_players_dict

    with cols[8]:

        manager_badges = " ".join(
            f":green-badge[{manager}]"
            if manager == st.session_state[f"{page_name}_my_manager_key"]
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

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Players per role**")

    for i, role, role_with_aka, value in zip(range(2,9,2), roles_list, roles_with_aka_list, [3,8,8,6]):
        with cols[i]:
            role_limit_key = f"{page_name}_{role}_limit_key"
            settings_keys_set.add(role_limit_key)
            st.session_state.setdefault(role_limit_key, value)
            goalkeepers_limit = st.number_input(
                f"Number of {str(role).capitalize()} {str(role_with_aka).split(' ')[1]}",
                min_value=0,
                step=1,
                key=role_limit_key,
            )

# Budget limits settings
with st.container(border=True):

    cols = st.columns([8,1,6,1,6,1,6,1,6,1,6])

    with cols[0]:
        st.markdown("#### **Budget limits per role**")

    with cols[2]:
        budget_key = f"{page_name}_budget_key"
        settings_keys_set.add(budget_key)
        st.session_state.setdefault(budget_key, 500)
        budget = st.number_input(
            "Total Budget",
            min_value=0,
            step=50,
            key=budget_key,
        )

    cols = st.columns([8,1,6,1,6,1,6,1,6,1,6], vertical_alignment="center")

    budget_limits = []
    for i, role, role_with_aka, value in zip(range(2,9,2), roles_list, roles_with_aka_list, [50,100,200,150]):
        with cols[i]:
            role_budget_limit_key = f"{page_name}_{role}_budget_limit_key"
            settings_keys_set.add(role_budget_limit_key)
            st.session_state.setdefault(role_budget_limit_key, value)
            budget_limits.append(
                st.number_input(
                    f"Budget for {str(role).capitalize()}s",
                    min_value=0,
                    max_value=500,
                    step=5,
                    key=role_budget_limit_key,
                )
            )

    budget_limit_sum = sum(budget_limits)
    tot_budget = int(st.session_state[f"{page_name}_budget_key"])
    available_budget = tot_budget - budget_limit_sum
    available_budget_color = "green" if available_budget > 0 else "red"
    left_or_exceed = "left" if available_budget > 0 else "exceed"

    with cols[10]:
        if available_budget != 0:
            available_budget_str = f"{available_budget}" if available_budget < 0 else f"+{available_budget}"
            st.metric(
                label=f"Available mln",
                value=f":{available_budget_color}[{available_budget_str}] mln",
                icon="💰",
                border=True
            )
        else:
            st.metric(
                label=f"Available mln",
                value=f":green[✓] 0 mln",
                icon="💰",
                border=True
            )

# Graphics settings
with st.container(border=True):

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **Graphics per role**")

    for i, role in zip(range(2,9,2), roles_list):
        with cols[i]:
            st.markdown(f"**{str(role).capitalize()} statistics**")

            graphical_cols_key = f"{page_name}_{role}_graphical_cols_key"
            settings_keys_set.add(graphical_cols_key)
            st.session_state.setdefault(graphical_cols_key, [])
            for column_idx, column in enumerate(st.session_state[graphical_cols_key]):
                with st.container(border=True):
                    col1, col2 = st.columns([8,2], vertical_alignment="center")
                    with col1:
                        st.markdown(f"{get_user_view_of_column(column)}")
                    with col2:
                        remove_graphical_col_button = st.button(
                            "",
                            icon=":material/delete:",
                            type="tertiary",
                            help="Remove this statistic",
                            width="stretch",
                            key=f"{page_name}_remove_{role}_graphical_col_{column_idx}_key"
                        )
                if remove_graphical_col_button:
                    st.session_state[graphical_cols_key].remove(column)
                    st.rerun()


    cols = st.columns([8,1,8,1,8,1,8,1,8])
    for i, role in zip(range(2,9,2), roles_list):

        numeric_columns = [
            column for column in history_players.select_dtypes(include="number").columns.tolist()
            if column not in st.session_state[f"{page_name}_{role}_graphical_cols_key"]
        ]

        with cols[i]:
            st.divider()

            selected_graphical_col = st.selectbox(
                "Select a field to use for statistics",
                options=numeric_columns,
                index=None,
                placeholder="Select a column...",
                format_func=get_user_view_of_column,
                key=f"{page_name}_add_{role}_graphical_col_widget_key",
            )

            add_graphical_col_button = st.button(
                "Add",
                width="stretch",
                disabled=selected_graphical_col is None,
                key=f"{page_name}_add_button_{role}_graphical_col_key"
            )
            if add_graphical_col_button and selected_graphical_col is not None:
                st.session_state[f"{page_name}_{role}_graphical_cols_key"].append(selected_graphical_col)
                st.rerun()

# AI settings
with st.container(border=True):

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        st.markdown("#### **AI settings**")

    with cols[2]:
        ai_enabled_key = f"{page_name}_ai_enabled_key"
        settings_keys_set.add(ai_enabled_key)
        st.session_state.setdefault(ai_enabled_key, False)
        ai_enabled = st.toggle(
            "Activate AI to help you",
            key=ai_enabled_key,
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
    
fantacalcio_bought_players_df_key = f"{page_name}_fantacalcio_bought_players_df_key"
settings_keys_set.add(fantacalcio_bought_players_df_key)
st.session_state[fantacalcio_bought_players_df_key] = bought_players_df

# Store only persistent Session State values
settings_keys_list = list(settings_keys_set)
store_env(
    data_dict={key: st.session_state[key] for key in settings_keys_list if key in st.session_state},
    path=".env"
)
