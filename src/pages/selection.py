from pathlib import Path
import pandas as pd
import streamlit as st
from lib.utils import (
    highlight_player_role,
    set_format_interest,
    get_ai_icon,
    get_teams_dict,
    get_circular_role_icon,
    get_color_per_role,
    interest_markers
)
from lib.streamlit_api import (
    sync_filter,
    apply_filters,
    get_roles_dict,
    get_user_view_of_column,
    load_dataset,
    load_models,
    load_env,
    store_env,
)
from lib.xgboost_predictor import (
    features_to_predict_list,
)


st.set_page_config(
    page_title="Players Selection",
    page_icon=get_ai_icon(),
    layout="wide",
)

page_name = "selection"

columns_to_filter_list = [
    "R",
    "Nome",
    "Squadra",
]

compare_op_for_columns_to_filter_dict = {
    "Nome": None,
    "R": "eq",
    "Squadra": "eq",
}

hidden_selection_columns = [
    "Id",
    "RM",
    "Qt.A M",
    "Qt.I M",
    "Diff.M",
    "FVM",
    "FVM M",
    "Qt.A",
    "Qt.I",
    "Diff."
]

interest_colors_dict = {
    "Da valutare": "#E0E0E0",
    "Bassissimo": "#FFFFFF",
    "Basso": "#FFF59D",
    "Medio": "#FFCC80",
    "Alto": "#EF9A9A",
    "Scommessa": "#81D4FA",
    "Buoni low cost": "#81FAC8",
}


# =============================================================================
# ============================== FUNCTIONS ====================================
# =============================================================================

def players_filters(players: pd.DataFrame, columns_to_filter_list: list[str]) -> pd.DataFrame:
    """Display independent Fantacalcio player filters in the sidebar."""
    cols = st.columns([4,1,4,1,4,1,4,1,4])

    # Player selection
    player_filter_key = f"{page_name}_Nome_key"
    player_widget_key = f"{page_name}_Nome_widget_key"
    selection_keys_set.update({player_filter_key})
    player_options = sorted(players["Nome"].dropna().unique(), key=str)
    with cols[6]:
        st.selectbox(
            "Search a player",
            options=player_options,
            index=None,
            placeholder="Select a player...",
            key=player_widget_key,
            on_change=sync_player_filter,
            args=(player_widget_key, player_filter_key)
        )

    # Team selection
    team_filter_key = f"{page_name}_Squadra_key"
    team_widget_key = f"{page_name}_Squadra_widget_key"
    selection_keys_set.update({team_filter_key})
    team_options = sorted(players["Squadra"].dropna().unique(), key=str)
    with cols[8]:
        st.multiselect(
            "Select teams",
            options=team_options,
            placeholder="Select one or more teams...",
            key=team_widget_key,
            on_change=sync_filter,
            args=(team_filter_key, team_widget_key),
        )

    # Fanta role selection
    role_filter_key = f"{page_name}_R_key"
    role_widget_key = f"{page_name}_R_widget_key"
    selection_keys_set.update({role_filter_key})
    role_options = get_roles_dict().keys()
    with cols[0]:
        st.pills(
            "Select a role",
            options=role_options,
            selection_mode="multi",
            key=role_widget_key,
            on_change=sync_filter,
            args=(role_filter_key, role_widget_key),
        )

    # Apply filters only to the returned data
    filtered_players = apply_filters(
        players,
        columns_to_filter_list=columns_to_filter_list,
        compare_op_for_columns_to_filter_dict=compare_op_for_columns_to_filter_dict,
        page=page_name,
    )

    st.session_state[f"{page_name}_filtered_selection_players_key"] = filtered_players
    return filtered_players


def sync_player_filter(widget_key, key) -> None:
    selected_value = st.session_state.get(widget_key)
    st.session_state[key] = [selected_value] if selected_value is not None else []


def get_configured_statistics_columns(selected_roles: list[str]) -> list[str]:
    """Return the union of the statistics configured for the selected roles."""
    roles_dict = get_roles_dict()
    roles = [role for role in roles_dict if not selected_roles or role in selected_roles]
    statistics_columns = []

    for role in roles:
        role_columns = st.session_state.get(
            f"settings_{role}_graphical_cols_key",
            [],
        )
        for column in role_columns:
            if column not in statistics_columns:
                statistics_columns.append(column)

    return statistics_columns


def add_latest_player_statistics(players: pd.DataFrame, history_players: pd.DataFrame, statistics_columns: list[str]) -> pd.DataFrame:
    """Add the latest available statistics without duplicating player rows."""
    players_with_statistics = players.copy()

    available_columns = [
        column
        for column in statistics_columns
        if column in history_players.columns and column not in players.columns
    ]
    if not available_columns or "id" not in history_players.columns:
        return players_with_statistics

    lookup_columns = ["id", "season", "minutes"] + available_columns
    lookup_columns = list(dict.fromkeys(column for column in lookup_columns if column in history_players.columns))
    statistics_lookup = history_players[lookup_columns].copy()
    statistics_lookup = statistics_lookup[statistics_lookup[available_columns].notna().any(axis=1)]

    if statistics_lookup.empty:
        for column in available_columns:
            players_with_statistics[column] = pd.NA
        return players_with_statistics

    if "season" in statistics_lookup:
        statistics_lookup["_season_sort"] = statistics_lookup["season"].astype(str)
    else:
        statistics_lookup["_season_sort"] = ""
    if "minutes" in statistics_lookup:
        statistics_lookup["_minutes_sort"] = pd.to_numeric(statistics_lookup["minutes"], errors="coerce").fillna(0)
    else:
        statistics_lookup["_minutes_sort"] = 0

    latest_statistics = statistics_lookup.sort_values(["id", "_season_sort", "_minutes_sort"]).drop_duplicates("id", keep="last").set_index("id")
    for column in available_columns:
        players_with_statistics[column] = players_with_statistics["Id"].map(latest_statistics[column])

    return players_with_statistics


def get_stats_player_key(field: str, player_id) -> str:
    """Return the persistent Session State key for one player field."""
    return f"{page_name}_{field}_{player_id}_key"


def update_player_selections(player_ids: tuple, editor_key: str) -> None:
    """Synchronize checkbox edits with the persistent player state."""
    edited_rows = st.session_state[editor_key]["edited_rows"]
    for row_position, changes in edited_rows.items():
        if "selected" in changes:
            player_id = player_ids[int(row_position)]
            st.session_state[get_stats_player_key("selected", player_id)] = bool(changes["selected"])


def remove_selected_player(player_ids: tuple, button_key: str) -> None:
    """Remove the player associated with the clicked table button."""
    click = st.session_state.get(button_key)
    if click is None:
        return

    player_id = player_ids[click["row"]]
    st.session_state[get_stats_player_key("selected", player_id)] = False


def load_selected_players(path: str) -> None:
    """Restore selected players and their editable fields from a CSV file."""
    try:
        selection_players = pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return

    for _, player_row in selection_players.iterrows():
        player_id = player_row["Id"]
        if pd.isna(player_id):
            continue
        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)

        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")
        interest = player_row["interest"]
        description = player_row["description"]

        if interest not in interest_colors_dict:
            interest = "Da valutare"

        st.session_state[get_stats_player_key("selected", player_id)] = True
        st.session_state[get_stats_player_key("mln", player_id)] = 0 if pd.isna(mln_value) else int(mln_value)
        st.session_state[get_stats_player_key("interest", player_id)] = interest
        st.session_state[get_stats_player_key("description", player_id)] = "" if pd.isna(description) else str(description)

    return


def store_selected_players(players: pd.DataFrame, path: str) -> None:
    """Overwrite the CSV file with the currently selected players."""
    selection_players = []

    for player_id in players["Id"]:
        selected_key = get_stats_player_key("selected", player_id)

        # Case of non-selected player
        if not st.session_state.get(selected_key, False):
            continue
        
        # Creation of the keys
        mln_key = get_stats_player_key("mln", player_id)
        interest_key = get_stats_player_key("interest", player_id)
        description_key = get_stats_player_key("description", player_id)

        # Append of the new row to store
        selection_players.append(
            {
                "Id": player_id,
                "mln": st.session_state.get(mln_key, 0),
                "interest": st.session_state.get(interest_key, "Da valutare"),
                "description": st.session_state.get(description_key, ""),
            }
        )

    # Write into the file
    selection_players_df = pd.DataFrame(
        selection_players,
        columns=["Id", "mln", "interest", "description"],
    )
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    selection_players_df.to_csv(csv_path, index=False)
    return


def get_selection_column_config(columns: list[str], players: pd.DataFrame) -> dict:
    """Create readable Streamlit column configurations for selection tables."""
    integer_statistics_columns = {"age", "birth_year", "appearances", "starts", "minutes"}
    float_statistics_columns = {
        column
        for column in players.select_dtypes(include="float").columns
        if column not in integer_statistics_columns
    }
    statistics_number_formats = {
        **dict.fromkeys(integer_statistics_columns, "%d"),
        **dict.fromkeys(float_statistics_columns, "%.2f"),
    }

    column_config = {
        column: (
            st.column_config.NumberColumn(
                get_user_view_of_column(column),
                format=statistics_number_formats[column],
                alignment="center",
            )
            if column in statistics_number_formats
            else st.column_config.Column(
                get_user_view_of_column(column),
                alignment="center",
            )
        )
        for column in columns
    }

    if "selected" in columns:
        column_config["selected"] = st.column_config.CheckboxColumn(
            get_user_view_of_column("selected"),
            help="Add or remove this player from your selection.",
            default=False,
            pinned=True,
            alignment="center",
        )
    if "mln" in columns:
        column_config["mln"] = st.column_config.NumberColumn(
            get_user_view_of_column("mln"),
            help="Maximum number of credits you would spend for this player.",
            min_value=0,
            step=1,
            format="%d",
            required=True,
            alignment="center",
        )
    if "interest" in columns:
        column_config["interest"] = st.column_config.SelectboxColumn(
            get_user_view_of_column("interest"),
            help="Choose your current interest in this player.",
            options=list(interest_colors_dict),
            format_func=set_format_interest,
            default="Da valutare",
            required=True,
        )
    if "description" in columns:
        column_config["description"] = st.column_config.TextColumn(
            get_user_view_of_column("description"),
            help="Write a short note about this player.",
            default="",
            width="large",
            alignment="center",
        )

    return column_config


def create_player_selection_table2(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display filtered players with persistent checkboxes and AI icons."""
    
    players_editor_df = players.set_index("Id")[visible_columns].copy()

    rows = []
    for player_id, player_row in players_editor_df.iterrows():
        selected_key = get_stats_player_key("selected", player_id)
        st.session_state.setdefault(selected_key, False)

        player_values = {}
        for column in visible_columns:
            value = player_row[column]
            if pd.isna(value):
                player_values[column] = ""
            elif pd.api.types.is_float_dtype(players_editor_df[column].dtype):
                player_values[column] = f"{float(value):.2f}"
            elif pd.api.types.is_integer_dtype(players_editor_df[column].dtype):
                player_values[column] = str(int(value))
            else:
                player_values[column] = str(value)

        row_styles = highlight_player_role(player_row)
        rows.append(
            {
                "id": player_id.item() if hasattr(player_id, "item") else player_id,
                "selected": bool(st.session_state[selected_key]),
                "values": player_values,
                "readonlyStyle": row_styles[0] if row_styles else "",
            }
        )

    columns = [
        {
            "key": "selected",
            "label": get_user_view_of_column("selected"),
            "prediction": False,
        }
    ]
    columns.extend(
        {
            "key": column,
            "label": get_user_view_of_column(column),
            "prediction": str(column).lower().startswith("pred_"),
        }
        for column in visible_columns
    )

    ai_icon = get_ai_icon()
    ai_icon_src = ai_icon.removeprefix("![AI](").removesuffix(")")
    component_key = f"{page_name}_players_selection_icon_component_key"

    def update_player_selection() -> None:
        component_state = st.session_state.get(component_key, {})
        selection = component_state.get("selected")
        if not selection:
            return

        player_id = selection["id"]
        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)
        st.session_state[get_stats_player_key("selected", player_id)] = bool(selection["value"])

    component_renderer = getattr(
        create_player_selection_table2,
        "_component_renderer",
        None,
    )
    if component_renderer is None:
        component_renderer = st.components.v2.component(
            "selection_player_selection_table_with_icon",
            html='<div id="player-selection-table-root"></div>',
            css="""
            .table-wrapper {
                width: 100%;
                height: 450px;
                overflow: auto;
                border: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                border-radius: var(--st-base-radius);
            }

            table {
                width: max-content;
                min-width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                color: var(--st-text-color);
                font-family: var(--st-font);
                font-size: 0.875rem;
            }

            th, td {
                box-sizing: border-box;
                min-width: 105px;
                height: 38px;
                padding: 6px 10px;
                border-right: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                border-bottom: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                text-align: center;
                white-space: nowrap;
            }

            th {
                position: sticky;
                top: 0;
                z-index: 1;
                background: var(--st-dataframe-header-background-color, var(--st-secondary-background-color));
                font-weight: 600;
            }

            th:last-child, td:last-child {
                border-right: 0;
            }

            .header-content {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
            }

            .header-icon {
                width: 22px;
                height: 22px;
                object-fit: contain;
            }

            .selection-column {
                position: sticky;
                left: 0;
                z-index: 1;
                min-width: 70px;
                width: 70px;
                background: var(--st-background-color);
            }

            th.selection-column {
                z-index: 2;
                background: var(--st-dataframe-header-background-color, var(--st-secondary-background-color));
            }

            input[type="checkbox"] {
                width: 17px;
                height: 17px;
                accent-color: var(--st-primary-color);
                cursor: pointer;
            }
            """,
            js="""
            export default function(component) {
                const { data, parentElement, setTriggerValue } = component;
                const root = parentElement.querySelector("#player-selection-table-root");
                if (!root) return;

                root.replaceChildren();
                const wrapper = document.createElement("div");
                wrapper.className = "table-wrapper";
                const table = document.createElement("table");
                const head = document.createElement("thead");
                const headRow = document.createElement("tr");

                data.columns.forEach((column) => {
                    const header = document.createElement("th");
                    if (column.key === "selected") {
                        header.className = "selection-column";
                    }

                    const content = document.createElement("div");
                    content.className = "header-content";
                    if (column.prediction) {
                        const icon = document.createElement("img");
                        icon.className = "header-icon";
                        icon.src = data.aiIconSrc;
                        icon.alt = "AI";
                        content.appendChild(icon);
                    }

                    const label = document.createElement("span");
                    label.textContent = column.label;
                    content.appendChild(label);
                    header.appendChild(content);
                    headRow.appendChild(header);
                });

                head.appendChild(headRow);
                table.appendChild(head);
                const body = document.createElement("tbody");

                data.rows.forEach((row) => {
                    const tableRow = document.createElement("tr");
                    data.columns.forEach((column) => {
                        const cell = document.createElement("td");

                        if (column.key === "selected") {
                            cell.className = "selection-column";
                            const checkbox = document.createElement("input");
                            checkbox.type = "checkbox";
                            checkbox.checked = row.selected;
                            checkbox.setAttribute(
                                "aria-label",
                                `Select player ${row.id}`,
                            );
                            checkbox.onchange = () => setTriggerValue(
                                "selected",
                                {id: row.id, value: checkbox.checked},
                            );
                            cell.appendChild(checkbox);
                        } else {
                            cell.textContent = row.values[column.key] ?? "";
                            cell.style.cssText = row.readonlyStyle;
                        }

                        tableRow.appendChild(cell);
                    });
                    body.appendChild(tableRow);
                });

                table.appendChild(body);
                wrapper.appendChild(table);
                root.appendChild(wrapper);
            }
            """,
        )
        create_player_selection_table2._component_renderer = component_renderer

    component_renderer(
        key=component_key,
        data={
            "columns": columns,
            "rows": rows,
            "aiIconSrc": ai_icon_src,
        },
        width="stretch",
        height=450,
        on_selected_change=update_player_selection,
    )


def create_player_selection_table(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display the filtered Fantacalcio players with persistent checkboxes."""
    players_editor_df = players.set_index("Id")[visible_columns].copy()

    selected_values = []
    for player_id in players_editor_df.index:
        selected_key = get_stats_player_key("selected", player_id)
        st.session_state.setdefault(selected_key, False)
        selected_values.append(bool(st.session_state[selected_key]))

    players_editor_df.insert(
        0,
        "selected",
        pd.Series(
            selected_values,
            index=players_editor_df.index,
            dtype=bool,
        ),
    )

    column_order = ["selected"] + visible_columns
    column_config = get_selection_column_config(column_order, players_editor_df)
    editor_data = players_editor_df.style.apply(
        highlight_player_role,
        axis=1,
        subset=visible_columns,
    )

    editor_key = f"{page_name}_players_selection_editor_key"
    st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        height=450,
        column_order=column_order,
        disabled=visible_columns,
        column_config=column_config,
        key=editor_key,
        on_change=update_player_selections,
        args=(tuple(players_editor_df.index), editor_key),
    )


def create_selected_players_table_css(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display the selected players with image icons in prediction headers."""
    selected_player_ids = []
    for player_id in players["Id"]:
        selected_key = get_stats_player_key("selected", player_id)
        if st.session_state.get(selected_key, False):
            selected_player_ids.append(player_id)

    if not selected_player_ids:
        return

    fanta_role = players["R"].iloc[0]
    selected_players_df = players[players["Id"].isin(selected_player_ids)]
    selected_players_df = selected_players_df.set_index("Id")[visible_columns].copy()

    rows = []
    for player_id, player_row in selected_players_df.iterrows():
        selected_key = get_stats_player_key("selected", player_id)
        mln_key = get_stats_player_key("mln", player_id)
        interest_key = get_stats_player_key("interest", player_id)
        description_key = get_stats_player_key("description", player_id)

        st.session_state.setdefault(selected_key, True)
        st.session_state.setdefault(mln_key, 1)
        st.session_state.setdefault(interest_key, "Da valutare")
        st.session_state.setdefault(description_key, "")

        mln_value = pd.to_numeric(st.session_state[mln_key], errors="coerce")
        mln_value = 0 if pd.isna(mln_value) else int(mln_value)
        interest = st.session_state[interest_key]
        if interest not in interest_colors_dict:
            interest = "Da valutare"
        description = st.session_state[description_key]
        description = "" if pd.isna(description) else str(description)

        st.session_state[mln_key] = mln_value
        st.session_state[interest_key] = interest
        st.session_state[description_key] = description

        player_values = {}
        for column in visible_columns:
            value = player_row[column]
            if pd.isna(value):
                player_values[column] = ""
            elif pd.api.types.is_float_dtype(selected_players_df[column].dtype):
                player_values[column] = f"{float(value):.2f}"
            elif pd.api.types.is_integer_dtype(selected_players_df[column].dtype):
                player_values[column] = str(int(value))
            else:
                player_values[column] = str(value)

        row_styles = highlight_player_role(player_row)
        rows.append(
            {
                "id": player_id.item() if hasattr(player_id, "item") else player_id,
                "mln": mln_value,
                "interest": interest,
                "description": description,
                "values": player_values,
                "readonlyStyle": row_styles[0] if row_styles else "",
            }
        )

    columns = [
        {"key": "remove", "label": "", "type": "remove", "prediction": False},
        {"key": "mln", "label": get_user_view_of_column("mln"), "type": "number", "prediction": False},
        {"key": "interest", "label": get_user_view_of_column("interest"), "type": "select", "prediction": False},
        {"key": "description", "label": get_user_view_of_column("description"), "type": "text", "prediction": False},
    ]
    columns.extend(
        {
            "key": column,
            "label": get_user_view_of_column(column),
            "type": "readonly",
            "prediction": str(column).lower().startswith("pred_"),
        }
        for column in visible_columns
    )

    ai_icon = get_ai_icon()
    ai_icon_src = ai_icon.removeprefix("![AI](").removesuffix(")")
    component_key = f"{page_name}_selected_players_{fanta_role}_icon_component_key"

    def update_edited_player() -> None:
        component_state = st.session_state.get(component_key, {})
        edited = component_state.get("edited")
        if not edited:
            return

        player_id = edited["id"]
        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)

        field = edited["field"]
        value = edited["value"]
        if field == "mln":
            mln_value = pd.to_numeric(value, errors="coerce")
            st.session_state[get_stats_player_key(field, player_id)] = (
                0 if pd.isna(mln_value) else max(0, int(mln_value))
            )
        elif field == "interest":
            st.session_state[get_stats_player_key(field, player_id)] = (
                value if value in interest_colors_dict else "Da valutare"
            )
        elif field == "description":
            st.session_state[get_stats_player_key(field, player_id)] = str(value)

    def remove_player() -> None:
        component_state = st.session_state.get(component_key, {})
        player_id = component_state.get("removed")
        if player_id is None:
            return
        if isinstance(player_id, float) and player_id.is_integer():
            player_id = int(player_id)
        st.session_state[get_stats_player_key("selected", player_id)] = False

    component_renderer = getattr(
        create_selected_players_table_css,
        "_component_renderer",
        None,
    )
    if component_renderer is None:
        component_renderer = st.components.v2.component(
            "selection_selected_players_table_with_icon",
            html='<div id="selected-players-table-root"></div>',
            css="""
            .table-wrapper {
                width: 100%;
                overflow-x: auto;
                border: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                border-radius: var(--st-base-radius);
            }

            table {
                width: max-content;
                min-width: 100%;
                border-collapse: separate;
                border-spacing: 0;
                color: var(--st-text-color);
                font-family: var(--st-font);
                font-size: 0.875rem;
            }

            th, td {
                box-sizing: border-box;
                min-width: 105px;
                height: 38px;
                padding: 6px 10px;
                border-right: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                border-bottom: 1px solid var(--st-dataframe-border-color, var(--st-border-color));
                text-align: center;
                white-space: nowrap;
            }

            th {
                background: var(--st-dataframe-header-background-color, var(--st-secondary-background-color));
                font-weight: 600;
            }

            tr:last-child td {
                border-bottom: 0;
            }

            th:last-child, td:last-child {
                border-right: 0;
            }

            .header-content {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
            }

            .header-icon {
                width: 22px;
                height: 22px;
                object-fit: contain;
            }

            .remove-column {
                min-width: 48px;
                width: 48px;
            }

            .description-column {
                min-width: 220px;
            }

            input, select {
                box-sizing: border-box;
                width: 100%;
                min-height: 30px;
                padding: 4px 7px;
                color: var(--st-text-color);
                background: var(--st-background-color);
                border: 1px solid var(--st-widget-border-color, var(--st-border-color));
                border-radius: var(--st-base-radius);
                font: inherit;
            }

            button {
                padding: 4px 7px;
                color: var(--st-red-text-color, var(--st-text-color));
                background: transparent;
                border: 0;
                border-radius: var(--st-button-radius);
                cursor: pointer;
                font-size: 1rem;
            }

            button:hover {
                background: var(--st-red-background-color, var(--st-secondary-background-color));
            }
            """,
            js="""
            export default function(component) {
                const { data, parentElement, setTriggerValue } = component;
                const root = parentElement.querySelector("#selected-players-table-root");
                if (!root) return;

                root.replaceChildren();
                const wrapper = document.createElement("div");
                wrapper.className = "table-wrapper";
                const table = document.createElement("table");
                const head = document.createElement("thead");
                const headRow = document.createElement("tr");

                data.columns.forEach((column) => {
                    const header = document.createElement("th");
                    if (column.type === "remove") header.className = "remove-column";
                    if (column.type === "text") header.className = "description-column";

                    const content = document.createElement("div");
                    content.className = "header-content";
                    if (column.prediction) {
                        const icon = document.createElement("img");
                        icon.className = "header-icon";
                        icon.src = data.aiIconSrc;
                        icon.alt = "AI";
                        content.appendChild(icon);
                    }

                    const label = document.createElement("span");
                    label.textContent = column.label;
                    content.appendChild(label);
                    header.appendChild(content);
                    headRow.appendChild(header);
                });

                head.appendChild(headRow);
                table.appendChild(head);
                const body = document.createElement("tbody");

                data.rows.forEach((row) => {
                    const tableRow = document.createElement("tr");
                    data.columns.forEach((column) => {
                        const cell = document.createElement("td");

                        if (column.type === "remove") {
                            cell.className = "remove-column";
                            const button = document.createElement("button");
                            button.type = "button";
                            button.textContent = "🗑";
                            button.title = "Remove this player from your selection.";
                            button.setAttribute("aria-label", button.title);
                            button.onclick = () => setTriggerValue("removed", row.id);
                            cell.appendChild(button);
                        } else if (column.type === "number") {
                            const input = document.createElement("input");
                            input.type = "number";
                            input.min = "0";
                            input.step = "1";
                            input.value = row.mln;
                            input.setAttribute("aria-label", column.label);
                            input.onchange = () => {
                                const value = Math.max(0, Math.trunc(Number(input.value) || 0));
                                input.value = value;
                                setTriggerValue("edited", {id: row.id, field: "mln", value});
                            };
                            cell.appendChild(input);
                        } else if (column.type === "select") {
                            const select = document.createElement("select");
                            select.setAttribute("aria-label", column.label);
                            data.interests.forEach((interest) => {
                                const option = document.createElement("option");
                                option.value = interest.value;
                                option.textContent = `${interest.marker} ${interest.value}`;
                                option.selected = interest.value === row.interest;
                                select.appendChild(option);
                            });
                            select.onchange = () => setTriggerValue(
                                "edited",
                                {id: row.id, field: "interest", value: select.value},
                            );
                            cell.appendChild(select);
                        } else if (column.type === "text") {
                            cell.className = "description-column";
                            const input = document.createElement("input");
                            input.type = "text";
                            input.value = row.description;
                            input.setAttribute("aria-label", column.label);
                            input.onchange = () => setTriggerValue(
                                "edited",
                                {id: row.id, field: "description", value: input.value},
                            );
                            cell.appendChild(input);
                        } else {
                            cell.textContent = row.values[column.key] ?? "";
                            cell.style.cssText = row.readonlyStyle;
                        }

                        tableRow.appendChild(cell);
                    });
                    body.appendChild(tableRow);
                });

                table.appendChild(body);
                wrapper.appendChild(table);
                root.appendChild(wrapper);
            }
            """,
        )
        create_selected_players_table_css._component_renderer = component_renderer

    component_renderer(
        key=component_key,
        data={
            "columns": columns,
            "rows": rows,
            "interests": [
                {"value": interest, "marker": marker}
                for interest, marker in interest_markers.items()
            ],
            "aiIconSrc": ai_icon_src,
        },
        width="stretch",
        height="content",
        on_edited_change=update_edited_player,
        on_removed_change=remove_player,
    )


def eval_players(players: pd.DataFrame):

    '''def eval_player(player: pd.DataFrame, team: dict) -> tuple:
        score = score_with_team = 0.0
        # Switch-case on player role
        if player['R'] == 'P':
            score = ((player['90s_stats_keeper']/38) * 0.50) + (player['CS%'] * 0.20) + (player['Save%'] * 0.10) + (player['Qt.A']/500)
            #print(f"score = {score} = {((player['90s_stats_keeper']/38) * 0.50)} + {(player['CS%'] * 0.20)} + {(player['Save%'] * 0.10)} + {(player['Qt.A']/500)}")
            score_with_team = score - score * 0.40 * (1 - (team['valutazione']/100)) - score * 0.40 * (team['gol_subiti']/max_team_gol_subiti)
        elif player['R'] == 'D':
            score = int('MF' in player['Pos']) * 10 + int('FW' in player['Pos']) * 20 + player['Gls'] * 3 + player['Ast'] * 2 + player['Tkl+Int'] * 0.50 + player['Diff.'] * 3 + player['Qt.A']
            score -= player['Err'] * 2 + player['CrdY'] * 0.50 + player['CrdR'] * 2
            score_with_team = score + score * 0.25 * (team['valutazione']/100) - score * 0.25 * (team['gol_subiti']/max_team_gol_subiti) + score * 0.10 * (team['gol_fatti']/100)
        elif player['R'] == 'C':
            score = int('FW' in player['Pos']) * 30 + player['Gls'] * 3 + player['Ast'] * 2 + player['Tkl+Int'] * 0.50 + player['Diff.'] * 3 + player['Qt.A']
            score -= player['Err'] * 2 + player['CrdY'] * 0.50 + player['CrdR'] * 2
            score_with_team = score + score * 0.30 * (team['valutazione']/100) + score * 0.20 * (team['gol_fatti']/100)
        elif player['R'] == 'A':
            score = player['Gls'] * 3 + player['Ast'] * 2 + player['Diff.'] + player['Qt.A']
            score -= player['Err'] * 2 + player['CrdY'] * 0.50 + player['CrdR'] * 2
            score_with_team = score + score * 0.30 * (team['valutazione']/100) - score * 0.20 * (team['gol_subiti']/max_team_gol_subiti) + score * 0.20 * (team['gol_fatti']/100)
        return score, score_with_team'''
    
    # Evaluation based on AI predictions + own team evaluation
    players
    teams_df = pd.DataFrame(get_teams_dict())

    return


def create_selected_players_table(players: pd.DataFrame, visible_columns: list[str]) -> None:
    """Display and edit the persistent shortlist of selected players."""
    selected_player_ids = []
    for player_id in players["Id"]:
        selected_key = get_stats_player_key("selected", player_id)
        if st.session_state.get(selected_key, False):
            selected_player_ids.append(player_id)

    if not selected_player_ids:
        return
    
    fanta_role = players['R'].iloc[0]

    selected_players_editor_df = players[players["Id"].isin(selected_player_ids)]
    selected_players_editor_df = selected_players_editor_df.set_index("Id")[visible_columns].copy()

    mln_values = []
    interest_values = []
    description_values = []

    for player_id in selected_players_editor_df.index:
        selected_key = get_stats_player_key("selected", player_id)
        mln_key = get_stats_player_key("mln", player_id)
        interest_key = get_stats_player_key("interest", player_id)
        description_key = get_stats_player_key("description", player_id)

        st.session_state.setdefault(selected_key, True)
        st.session_state.setdefault(mln_key, 0)
        st.session_state.setdefault(interest_key, "Da valutare")
        st.session_state.setdefault(description_key, "")

        mln_value = pd.to_numeric(st.session_state[mln_key], errors="coerce")
        mln_value = 0 if pd.isna(mln_value) else int(mln_value)
        interest = st.session_state[interest_key]
        if interest not in interest_colors_dict:
            interest = "Da valutare"
        description = st.session_state[description_key]
        description = "" if pd.isna(description) else str(description)

        st.session_state[mln_key] = mln_value
        st.session_state[interest_key] = interest
        st.session_state[description_key] = description

        mln_values.append(mln_value)
        interest_values.append(interest)
        description_values.append(description)

    selected_players_editor_df.insert(0, "description", description_values)
    selected_players_editor_df.insert(0, "interest", interest_values)
    selected_players_editor_df.insert(0, "mln", mln_values)
    selected_players_editor_df.insert(0, "remove", ":material/delete:")

    editable_columns = ["remove", "mln", "interest", "description"]
    column_order = editable_columns + visible_columns
    column_config = get_selection_column_config(column_order, selected_players_editor_df)
    for column, config in column_config.items():
        if str(column).lower().startswith("pred_"):
            config["label"] = f"{get_ai_icon()} {config['label']}"
    remove_button_key = f"{page_name}_{fanta_role}_remove_player_button_key"
    column_config["remove"] = st.column_config.ButtonColumn(
        "",
        help="Remove this player from your selection.",
        pinned=True,
        type="tertiary",
        on_click=remove_selected_player,
        args=(tuple(selected_players_editor_df.index), remove_button_key),
        key=remove_button_key,
    )
    editor_data = selected_players_editor_df.style.apply(
        highlight_player_role,
        axis=1,
        subset=visible_columns,
    )
    
    edited_selected_players = st.data_editor(
        editor_data,
        hide_index=True,
        width="stretch",
        column_order=column_order,
        disabled=visible_columns,
        column_config=column_config,
        key=f"{page_name}_selected_players_{fanta_role}_editor_key",
    )

    for player_id, player_row in edited_selected_players.iterrows():
        mln_key = get_stats_player_key("mln", player_id)
        interest_key = get_stats_player_key("interest", player_id)
        description_key = get_stats_player_key("description", player_id)

        interest = player_row["interest"]
        if interest not in interest_colors_dict:
            interest = "Da valutare"

        description = player_row["description"]
        description = "" if pd.isna(description) else str(description)
        mln_value = pd.to_numeric(player_row["mln"], errors="coerce")

        st.session_state[mln_key] = 0 if pd.isna(mln_value) else int(mln_value)
        st.session_state[interest_key] = interest
        st.session_state[description_key] = description


# =============================================================================
# =============================== SCRIPT ======================================
# =============================================================================

fanta_players = load_dataset("data/predicted_fanta_players.csv")
history_players = load_dataset("data/filtered_history_players.csv")
loaded_env_values = load_env(path=".env")
selection_keys_set = {key for key in loaded_env_values if key.startswith(f"{page_name}_")}
models_packages_dict = load_models(target_features=features_to_predict_list)

# Save the path to the csv file with selected players
selection_players_key = f"{page_name}_selected_players_csv_path_key"
st.session_state.setdefault(selection_players_key, "data/selection_players.csv")
selection_keys_set.add(selection_players_key)

# Load the selected players 
selection_restored_key = f"{page_name}_selection_players_restored_v2_key"
if not st.session_state.get(selection_restored_key, False):
    load_selected_players(st.session_state[selection_players_key])
    st.session_state[selection_restored_key] = True

st.title(f"{get_ai_icon()} Players Selection")
st.caption(
    "Build and manage your personal shortlist by selecting players, comparing the configured statistics, "
    "setting expected prices and interest levels, and adding notes for the auction."
)
st.divider()

# Create filters on the sidebar
filtered_players = players_filters(fanta_players, columns_to_filter_list)

# Filter the visible columns
selected_roles = st.session_state.setdefault(f"{page_name}_R_key", [])
selected_roles = st.session_state[f"{page_name}_R_key"]
statistics_columns = get_configured_statistics_columns(selected_roles)
filtered_players_with_statistics = add_latest_player_statistics(
    filtered_players,
    history_players,
    statistics_columns,
)

# Select the visible columns
base_visible_selection_columns = [
    col
    for col in filtered_players.columns
    if col not in hidden_selection_columns
]
visible_selection_columns = base_visible_selection_columns + [
    col
    for col in statistics_columns
    if col in filtered_players_with_statistics.columns
    and col not in base_visible_selection_columns
]
visible_selection_columns = [
    col
    for col in visible_selection_columns
    if not (
        str(col).lower().startswith("pred_")
        and filtered_players_with_statistics[col].isna().all()
    )
]

# Create the full table
create_player_selection_table2(filtered_players_with_statistics, visible_selection_columns)

st.divider()

# Create the selection table
for fanta_role, role_name in get_roles_dict().items():

    color_role = get_color_per_role(fanta_role, rgba=True)
    col1, col2= st.columns([1,29], vertical_alignment="center")
    with col1:
        st.markdown(f"{get_circular_role_icon(fanta_role, font_size=20, height=32, width=32, y_translation=5)}", unsafe_allow_html=True)
    with col2:
        st.markdown(
            f'### :color[{role_name.capitalize()}s selected]'
            f'{{foreground="{color_role}"}}',
        )

    tmp_df = fanta_players[fanta_players["R"] == fanta_role]
    if tmp_df.empty:
        st.info(f"Absent players with role {fanta_role}.")
        continue

    # Select the visible columns
    role_visible_selection_columns = [
        col
        for col in base_visible_selection_columns
        if col in tmp_df.columns
        and not (
            str(col).lower().startswith("pred_")
            and tmp_df[col].isna().all()
        )
    ]

    create_selected_players_table_css(tmp_df, role_visible_selection_columns)

# Store the selected players in a csv file
store_selected_players(fanta_players, st.session_state[selection_players_key])

selection_keys_list = list(selection_keys_set)
store_env(
    data_dict={
        key: st.session_state[key]
        for key in selection_keys_list
        if key in st.session_state
    },
    path=".env",
)
