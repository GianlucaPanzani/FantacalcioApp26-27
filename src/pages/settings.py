import streamlit as st
import pandas as pd
from lib.data_handler import (
    export_guest_state,
)
from lib.utils import auction_settings, get_current_season, get_current_date
from lib.streamlit_api.data_handler import (
    get_fanta_manager_players_dict,
    get_roles_dict,
    add_graphical_columns,
    load_dataset,
    load_persistent_state,
    store_persistent_state,
    restore_personal_backup
)
from lib.streamlit_api.design_handler import (
    bottom_caption,
    get_background_img_path,
    get_circular_role_icon,
    get_emoji,
    get_icon,
    get_user_view_of_column,
    set_page_background,
    set_color_background,
)


page_name = "settings"

st.set_page_config(
    page_title="Settings",
    page_icon=get_emoji(page_name),
    layout="wide",
)

img_path = get_background_img_path(page_name)
set_page_background(img_path)
set_color_background()


# Title
cols = st.columns([1,15])
with cols[0]:
    st.markdown(f"{get_icon('settings')}", unsafe_allow_html=True)
with cols[1]:
    st.title("Settings")
st.caption("Configure Fanta Managers, squad limits, budgets, auction rules, bonus and penalty points, and player charts.")

loaded_persistent_values = load_persistent_state(
    st.session_state["user_id_key"],
    page_names=[page_name],
)
settings_keys_set = {
    key
    for key in loaded_persistent_values
    if key.startswith(f"{page_name}_")
}

my_manager_key = f"{page_name}_my_manager_key"
settings_keys_set.add(my_manager_key)
st.session_state.setdefault(my_manager_key, "Me")

managers_key = f"{page_name}_managers_key"
settings_keys_set.add(managers_key)
st.session_state.setdefault(managers_key, [st.session_state[my_manager_key]])

ai_enabled_key = f"{page_name}_ai_enabled_key"
settings_keys_set.add(ai_enabled_key)
st.session_state.setdefault(ai_enabled_key, False)

my_fanta_manager = st.session_state[f"{page_name}_my_manager_key"]

# Reorder the Fanta Managers with my Fanta Manager as first item
fanta_managers = st.session_state[f"{page_name}_managers_key"]
fanta_managers = [my_fanta_manager] + [manager for manager in fanta_managers if manager != my_fanta_manager]
st.session_state[f"{page_name}_managers_key"] = fanta_managers

# Getting data
fanta_manager_players_dict = get_fanta_manager_players_dict()
history_players = load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv")


# Fanta Managers settings
with st.container(border=True, key=f"dark-card-{page_name}_fanta_managers_key"):

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        col1, col2 = st.columns([1,8])
        with col1:
            st.markdown("#### 👥")
        with col2:
            st.markdown("#### **Fanta Managers**")

    with cols[2]:

        new_my_fanta_manager = st.text_input(
            label="Your Fanta Manager name",
            placeholder=st.session_state[f"{page_name}_my_manager_key"],
            key=f"{page_name}_my_manager_widget_key",
        ).capitalize().strip()

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
        ).capitalize().strip()

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
                st.success("New Fanta Manager added")
        if remove_fanta_manager_button:
            if remove_warning:
                st.info(remove_warning)
            else:
                st.success("Fanta Manager removed")

# Squad size settings
with st.container(border=True, key=f"dark-card-{page_name}_auction_key"):

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        col1, col2 = st.columns([1,8])
        with col1:
            st.markdown("#### ⚽")
        with col2:
            st.markdown("#### **Players per role**")

    for i, (role, role_name), default_value in zip(range(2,9,2), get_roles_dict().items(), [3,8,8,6]):
        role_limit_widget_key = f"{page_name}_{role}_limit_widget_key"
        st.session_state.setdefault(role_limit_widget_key, default_value)
        settings_keys_set.add(role_limit_widget_key)

        with cols[i]:
            st.number_input(
                f"Number of maximum {str(role_name).capitalize()}s",
                min_value=0,
                step=1,
                key=role_limit_widget_key,
            )

# Budget limits settings
with st.container(border=True, key=f"dark-card-{page_name}_budgets_key"):
    budget_widget_key = f"{page_name}_budget_widget_key"
    budget_limits_sum_key = f"{page_name}_budget_limits_sum_key"

    st.session_state.setdefault(budget_widget_key, 500)
    st.session_state.setdefault(budget_limits_sum_key, 500)
    settings_keys_set.add(budget_widget_key)

    cols = st.columns([8,1,8,1,8,1,8,1,8])

    with cols[0]:
        col1, col2 = st.columns([1,8])
        with col1:
            st.markdown("#### 💰")
        with col2:
            st.markdown("#### **Budget limits per role**")

    with cols[2]:
        budget = st.number_input(
            "Total Budget",
            min_value=250,
            max_value=1000,
            step=50,
            key=budget_widget_key,
        )

    cols = st.columns([8,1,35])
    with cols[2]:
        with st.container(border=True, height="stretch", width="stretch"):
            sub_cols = st.columns([8,1,8,1,8,1,8])

            budget_limits = []
            availabel_budget_label = 0
            for i, (role, role_name), default_value in zip(range(0,7,2), get_roles_dict().items(), [50,100,150,200]):
                role_budget_limit_widget_key = f"{page_name}_{role}_budget_limit_widget_key"
                st.session_state.setdefault(role_budget_limit_widget_key, default_value)
                settings_keys_set.add(role_budget_limit_widget_key)
                
                with sub_cols[i]:
                    budget_limits.append(
                        st.number_input(
                            f"Budget for {str(role_name).capitalize()}s",
                            min_value=0,
                            max_value=st.session_state[budget_widget_key],
                            step=5,
                            key=role_budget_limit_widget_key,
                        )
                    )

                st.session_state[budget_limits_sum_key] = sum(budget_limits)
                availabel_budget_label += st.session_state[role_budget_limit_widget_key]

            tot_budget = int(st.session_state[budget_widget_key])
            available_budget = tot_budget - st.session_state[budget_limits_sum_key]
            left_or_exceed = "left" if available_budget > 0 else "exceed"
            available_budget_str = f"{available_budget}" if available_budget < 0 else f"+{available_budget}"
            
            if available_budget < 0:
                st.metric(
                    label=f"**Budget unbalanced**:", # {tot_budget} - {availabel_budget_label}",
                    value=f":red[:material/cancel:] :red[{available_budget_str}] mln",
                    height="stretch",
                    width="stretch",
                )
                st.caption(f"You should decrease by {available_budget_str} mln.")
            elif available_budget > 0:
                st.metric(
                    label=f"**Budget unbalanced**:", # {tot_budget} - {availabel_budget_label}",
                    value=f":red[:material/cancel:] :green[{available_budget_str}] mln",
                    height="stretch",
                    width="stretch",
                )
                st.caption(f"You should increase by {available_budget_str} mln.")
            else:
                st.metric(
                    label="**Budgets balanced**",
                    value=":green[:material/check_circle:] 0 mln",
                    height="stretch",
                    width="stretch",
                )
                st.caption(f"Now you're ready to play!")


# General auction rules and bonus/malus points
with st.container(border=True, key=f"dark-card-{page_name}_auction_rules_key"):

    # Initializations for auction widgets
    extraction_settings = {
        "player_extraction_type": (
            "Player extraction type",
            ["by_role", "on_all_players"],
            "on_all_players",
            {
                "by_role": "By role",
                "on_all_players": "On all players",
            },
        ),
        "role_extraction_order": (
            "Role extraction order",
            ["in_order_P_D_C_A", "random"],
            "in_order_P_D_C_A",
            {
                "in_order_P_D_C_A": "P → D → C → A",
                "random": "Random",
            },
        ),
        "player_extraction_order": (
            "Player extraction order",
            ["random", "alphabetic"],
            "random",
            {
                "random": "Random",
                "alphabetic": "Alphabetical",
            },
        ),
    }
    for setting_name, (_, _, default_value, _) in extraction_settings.items():
        widget_key = f"{page_name}_{setting_name}_widget_key"
        settings_keys_set.add(widget_key)
        st.session_state.setdefault(widget_key, default_value)
    auction_rule_settings = [
        ("defender_modifier", "Defender modifier"),
        ("midfielder_modifier", "Midfielder modifier"),
        ("player_switch", "Player switch"),
    ]
    for setting_name, _ in auction_rule_settings:
        widget_key = f"{page_name}_auction_{setting_name}_widget_key"
        settings_keys_set.add(widget_key)
        st.session_state.setdefault(widget_key, False)
    for setting_name, _, default_points, _, value_type in auction_settings:
        widget_key = f"{page_name}_points_{setting_name}_widget_key"
        settings_keys_set.add(widget_key)
        st.session_state.setdefault(widget_key, default_points)
        st.session_state[widget_key] = value_type(st.session_state[widget_key])

    cols = st.columns([8,1,8,1,8,1,8,1,8])
    with cols[0]:
        col1, col2 = st.columns([1,8])
        with col1:
            st.markdown("#### :material/gavel:")
        with col2:
            st.markdown("#### **Auction rules and points**")

    # Configure how players and roles are extracted during the auction
    for i, (setting_name, setting_config) in zip(range(2,8,2), extraction_settings.items()):
        label, options, _, labels = setting_config
        widget_key = f"{page_name}_{setting_name}_widget_key"

        with cols[i]:
            st.segmented_control(
                label,
                options=options,
                required=True,
                format_func=labels.get,
                key=widget_key,
                width="stretch",
                disabled=(
                    setting_name == "role_extraction_order"
                    and
                    st.session_state[f"{page_name}_player_extraction_type_widget_key"] == "on_all_players"
                ),
            )

    # Display bonus and penalty values on separate rows
    cols = st.columns([8,1,8,1,8,1,8,1,8])
    for row_start in range(0, len(auction_settings), 4):
        scoring_settings_chunk = auction_settings[row_start:row_start + 4]
        for i, (setting_name, label, default_value, help_str, type) in zip(range(2,9,2), scoring_settings_chunk):
            widget_key = f"{page_name}_points_{setting_name}_widget_key"
            with cols[i]:
                st.number_input(
                    label,
                    step=1 if type is int else 0.5,
                    format="%d" if type is int else "%.1f",
                    help=help_str,
                    key=widget_key,
                )
    
    # Display each auction rule once in the first row.
    cols = st.columns([8,1,8,1,8,1,8,1,8])
    for i, (setting_name, label) in zip(range(2,8,2), auction_rule_settings):
        widget_key = f"{page_name}_auction_{setting_name}_widget_key"

        with cols[i]:
            st.toggle(
                label,
                key=widget_key,
            )

# Graphics settings
with st.container(border=True, key=f"dark-card-{page_name}_graphics_key"):

    cols = st.columns([8,1,8,1,8,1,8,1,8])
    with cols[0]:
        col1, col2 = st.columns([1,8])
        with col1:
            st.markdown("#### 📊")
        with col2:
            st.markdown("#### **Graphics per role**")

    for i, (role, role_name) in zip(range(2,9,2), get_roles_dict().items()):
        with cols[i]:
            st.space(1)
            st.markdown(
                f"{get_circular_role_icon(role)} $\\quad$ **{str(role_name).capitalize()} statistics**",
                unsafe_allow_html=True
            )
            st.space(1)

            graphical_cols_key = f"{page_name}_{role}_graphical_cols_key"
            st.session_state.setdefault(graphical_cols_key, [])
            settings_keys_set.add(graphical_cols_key)

            if not st.session_state[graphical_cols_key]:
                st.info("No statistics selected")

            for i, column in enumerate(st.session_state[graphical_cols_key]):
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
                            key=f"{page_name}_remove_{role}_graphical_col_{i}_key"
                        )
                if remove_graphical_col_button:
                    st.session_state[graphical_cols_key].remove(column)
                    st.rerun()

    st.space(1)

    cols = st.columns([8,1,8,1,8,1,8,1,8])
    for i, role in zip(range(2,9,2), get_roles_dict().keys()):
        graphical_cols_key = f"{page_name}_{role}_graphical_cols_key"
        graphical_cols_widget_key = f"{page_name}_add_{role}_graphical_col_widget_key"
        settings_keys_set.add(graphical_cols_key)

        numeric_columns = [
            column for column in history_players.select_dtypes(include="number").columns.tolist()
            if column not in st.session_state[graphical_cols_key]
        ]

        with cols[i]:

            selected_graphical_cols = st.multiselect(
                "Select fields to use for statistics",
                options=numeric_columns,
                placeholder="Select columns...",
                format_func=get_user_view_of_column,
                key=graphical_cols_widget_key,
            )

            st.button(
                "Add",
                width="stretch",
                disabled=not selected_graphical_cols,
                key=f"{page_name}_add_button_{role}_graphical_col_key",
                on_click=add_graphical_columns,
                args=(graphical_cols_key, graphical_cols_widget_key),
            )

# Personal backup and restore
backup_upload_key = f"{page_name}_backup_upload_key"
backup_confirm_key = f"{page_name}_backup_confirm_key"
backup_result_key = f"{page_name}_backup_result_key"

with st.container(border=True, key=f"dark-card-{page_name}_backup_key"):
    col1, _, col2, _, col3 = st.columns([8,1,18,1,18])
    with col1:
        st.markdown("#### :material/settings_backup_restore: **Backup**")
        st.caption("Export or restore your personal settings, player selections and spending limits.")

    with col2:
        st.markdown(f"##### :material/upload: Backup upload")
        st.caption("Upload a previous backup to restore your personal settings, player selections, and spending limits.")

        uploaded_archive = st.file_uploader(
            "Upload a backup from FantAI",
            type=["zip"],
            key=backup_upload_key,
            help="Select a ZIP previously exported from FantAI.",
        )

        if uploaded_archive is not None:
            restore_confirmed = st.checkbox(
                "Replace my current personal settings with this backup",
                key=backup_confirm_key,
            )

            backup_stored = st.button(
                "Store uploaded backup",
                icon=":material/restore:",
                type="primary",
                width="stretch",
                disabled=not restore_confirmed,
                on_click=restore_personal_backup,
                args=(
                    backup_upload_key,
                    backup_result_key,
                    st.session_state["user_id_key"],
                    st.session_state["username_key"],
                ),
            )

            if backup_stored:
                backup_result = st.session_state[backup_result_key]
                if backup_result["success"]:
                    st.success(backup_result["message"])
                else:
                    st.error(backup_result["message"])

    with col3:
        st.markdown(f"##### :material/download: Backup download")
        st.caption("Download a backup of your personal settings, player selections, and spending limits.")

        download_disabled = False
        try:
            store_persistent_state(
                st.session_state["user_id_key"],
                {
                    key: st.session_state[key]
                    for key in settings_keys_set
                    if key in st.session_state
                },
            )
            backup_archive = export_guest_state(st.session_state["user_id_key"])
        except (ValueError, OSError) as error:
            backup_archive = None
            st.error(f"Unable to create the backup: {error}")
        if backup_archive is None:
            download_disabled = True

        st.download_button(
            "Download backup",
            data=backup_archive,
            file_name=f"FantAI_{get_current_season()}_backup_{get_current_date()}.zip",
            disabled=download_disabled,
            mime="application/zip",
            icon=":material/download:",
            width="stretch",
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
store_persistent_state(
    st.session_state["user_id_key"],
    {key: st.session_state[key] for key in settings_keys_list if key in st.session_state},
)

bottom_caption()
