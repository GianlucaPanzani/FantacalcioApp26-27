import altair as alt
import pandas as pd
import streamlit as st
import time

from lib.utils import columns_to_user_view_dict
from lib.shap_explainability import (
    build_model_explaination_response,
)
from lib.xgboost_predictor import (
    build_temporal_player_input,
    predict,
    get_transformed_feature_and_value,
    features_to_predict_per_role_dict
)
from lib.streamlit_api.data_handler import (
    get_role_budget_limits,
    get_role_limits,
    get_roles_dict,
    load_dataset,
)
from lib.streamlit_api.design_handler import (
    get_circular_role_icon,
    get_color_per_role,
    get_icon,
    get_user_view_of_column,
    set_player_card_background,
    set_text_size,
)


def ai_data_stream(text: str):
    """Yield text one word at a time for a short streaming animation."""
    words = text.split(" ")
    for index, word in enumerate(words):
        time.sleep(0.01)
        yield word + " " if index < len(words) - 1 else word



def get_player_img_url(player_name: str):
    """Return the player's cutout URL or the local fallback image path."""
    images_df = load_dataset("data/online_sources/players_thesportsdb.csv")
    img_player_row = images_df[images_df["query_name"] == player_name].iloc[0]
    if not img_player_row["found"] or pd.isna(img_player_row["strCutout"]) or img_player_row["strCutout"] == "":
        return "img/players/unknown.png"
    return img_player_row["strCutout"]


def print_ai_icon_with_markdown_title(markdown_text="### AI predictions"):
    """Display the AI icon beside a Markdown section title."""
    cols = st.columns([1,19])
    with cols[0]:
        st.markdown(get_icon("ai"))
    with cols[1]:
        st.markdown(markdown_text)


def highlight_bought_rows(row: pd.Series, fanta_managers: list[str]) -> list[str]:
    """Highlight purchased players, falling back to their role color."""
    my_manager_color = "#23C43E"
    other_managers_color = "#D44633"

    if row["bought"] == st.session_state["settings_my_manager_key"]:
        row_style = f"background-color: {my_manager_color}; color: #212121"
    elif row["bought"] in fanta_managers:
        row_style = f"background-color: {other_managers_color}; color: #212121"
    else:
        role_color = get_color_per_role(row.get("fanta_role", ""))
        row_style = (
            f"background-color: {role_color}; color: #212121"
            if role_color
            else ""
        )

    return [row_style] * len(row)


def print_models_predictions(
        models_packages_dict: dict,
        history_players: pd.DataFrame,
        history_of_the_player: pd.DataFrame,
        player_row: pd.Series,
        top_k=5,
        worst_k=2,
        explainability_enabled=True,
        plots_enebled=True
    ):
    """Display model predictions, optional charts and SHAP explanations.

    Params
    ----------
    models_packages_dict : dict
        Trained model packages indexed by predicted feature.
    history_players : pandas.DataFrame
        Historical dataset used to calculate role averages.
    history_of_the_player : pandas.DataFrame
        Historical rows for the selected player.
    player_row : pandas.Series
        Current Fantacalcio record for the selected player.
    top_k : int
        Number of strongest SHAP signals to display.
    worst_k : int
        Number of weakest SHAP signals to display.
    explainability_enabled : bool
        Whether to render model explanations.
    plots_enebled : bool
        Whether to render player-history charts.
    """
    features_explainability = load_dataset("data/csv/models_generated/features_explainability.csv")
    role_column_means = compute_role_column_means(history_players)

    print_ai_icon_with_markdown_title(markdown_text="### AI predictions")

    with st.container():
        col1, _, col2 = st.columns([9,1,40])

        # Create Fanta player title
        player_name = player_row["player"]
        fanta_role = player_row["fanta_role"]
        role_name = get_roles_dict()[fanta_role].capitalize()
        latest_team = player_row["Squadra"]
        role_badge_color = get_color_per_role(role=fanta_role, color_version=False)

        with col1:
            with st.container(border=True, width="stretch", key=f"dark-card-{player_name}_col1"):
                set_player_card_background()
                with st.container(border=True, horizontal_alignment="center", width="stretch", key=f"dark-card-player-portrait-{player_name}_col1"):
                    st.image(get_player_img_url(player_name))
                st.markdown(
                    f"##### {player_name}",
                    text_alignment="center",
                    width="stretch",
                    anchors=False,
                )
                st.markdown(
                    f":{role_badge_color}-badge[{role_name} ({fanta_role})]  \n:violet-badge[{latest_team}]",
                    text_alignment="center",
                )

        with col2:

            with st.container(border=True, width="stretch", key=f"dark-card-{player_name}_col2"):
                n_iters = len(features_to_predict_per_role_dict[fanta_role])

                if n_iters < 3:
                    cols = st.columns([9,1] * (n_iters-1) + [9])
                elif explainability_enabled or plots_enebled:
                    cols = st.columns([9,1,9,1,9])
                elif n_iters <= 5:
                    cols = st.columns([9,1] * (n_iters-1) + [9])
                else:
                    cols = st.columns([9,1,9,1,9,1,9])
                    
                n_cols = len(cols) + 1

                # Predict the minutes (used to do some calculus)
                minutes_package = models_packages_dict["minutes"]
                minutes_input = build_temporal_player_input(
                    player_history=history_of_the_player,
                    features=minutes_package["features"],
                )
                predicted_minutes = float(
                    predict(
                        model_package=minutes_package,
                        player_history=minutes_input,
                    )
                )
                predicted_minutes = max(0, min(predicted_minutes, 38 * 90))

                for i, feature in enumerate(features_to_predict_per_role_dict[fanta_role]):
                    model_package = models_packages_dict[feature]

                    # Build the dataframe input for the model to get the prediction
                    model_input = build_temporal_player_input(
                        player_history=history_of_the_player,
                        features=model_package["features"],
                    )
                    available_lags = model_input.attrs["available_lags"]
                    if available_lags == 0:
                        with cols[i*2 % n_cols]:
                            st.info(f"No historical seasons available for {columns_to_user_view_dict[feature]}.")
                        continue

                    prediction = predict(
                        model_package=model_package,
                        player_history=model_input,
                    )

                    with cols[i*2 % n_cols]:

                        # AI prediction
                        mean_value = role_column_means[fanta_role][feature]
                        _, mean_transformed_value = get_transformed_feature_and_value(
                            feature=feature,
                            pred_value=mean_value,
                            pred_minutes=predicted_minutes
                        )
                        transformed_feature, tranformed_value = get_transformed_feature_and_value(
                            feature=feature,
                            pred_value=prediction,
                            pred_minutes=predicted_minutes
                        )
                        with st.container(horizontal_alignment="center", border=True if plots_enebled or explainability_enabled else False):
                            st.metric(
                                label=f"**:blue[_{transformed_feature}_]**",
                                value=f":blue[{tranformed_value:.2f}]",
                                delta=f"{tranformed_value - mean_transformed_value:+.2f} [Mean: {mean_transformed_value}]",
                                delta_color="normal",
                                width="content",
                            )

                        # Case of plot enabled
                        if plots_enebled:
                            plot_player_history(
                                history_players=load_dataset("data/csv/notebooks_generated/serie_a_players_history.csv"),
                                player=player_name,
                                feature=feature,
                                seasons_to_plot=4,
                                disable_player_name=True,
                                models_packages_dict=models_packages_dict,
                            )

                        # Case of SHAP explainability enabled
                        st.session_state.setdefault(f"previous_explaination_for_{feature}_{player_name}", False)
                        if explainability_enabled:
                            explaination_response = build_model_explaination_response(
                                shap_explainer=model_package["explainer"],
                                features=model_package["features"],
                                features_explainability=features_explainability,
                                player_history=model_input,
                                top_k=top_k,
                                worst_k=worst_k
                            )
                            if not st.session_state[f"previous_explaination_for_{feature}_{player_name}"]:
                                st.session_state[f"previous_explaination_for_{feature}_{player_name}"] = True
                                st.write_stream(ai_data_stream(explaination_response))
                            else:
                                st.markdown(explaination_response)

    return


def create_player_history_chart(
        data: pd.DataFrame,
        statistic_name: str,
        y_limits=None,
        mean_value: float | None = None,
        prediction_data: pd.DataFrame | None = None,
        enable_collapse_values=False
):
    """Create a layered Altair chart for a player's seasonal history.

    Params
    ----------
    data : pandas.DataFrame
        Historical seasons, teams and values to plot.
    statistic_name : str
        Readable label for the vertical axis and tooltips.
    y_limits : sequence or None
        Optional minimum and maximum values for the vertical scale.
    mean_value : float or None
        Optional role average displayed as a reference line.
    prediction_data : pandas.DataFrame or None
        Optional predicted season and value displayed as a diamond marker.
    enable_collapse_values : bool
        Whether to average multiple team rows within each season.

    Returns
    -------
    altair.LayerChart
        Layered history, average and prediction chart.
    """
    data = data.copy()
    tooltip = [
        alt.Tooltip("season:N", title="Season"),
        alt.Tooltip("team:N", title="Team"),
        alt.Tooltip("value:Q", title=statistic_name),
    ]
    if enable_collapse_values and not data.empty:
        data["value"] = pd.to_numeric(data["value"], errors="coerce")
        data = data.dropna(subset=["value"])
        data["team"] = data["team"].fillna("Unknown team")
        data["team_value"] = data.apply(
            lambda row: f"{row['team']}: {row['value']:.2f}",
            axis=1,
        )
        data = data.groupby("season", sort=False, as_index=False).agg(
            value=("value", "mean"),
            team_values=("team_value", " | ".join),
            team_count=("team", "nunique"),
        )

    y_scale = alt.Scale(zero=False)
    if y_limits is not None:
        y_scale = alt.Scale(domain=list(y_limits), zero=False)

    season_order = data["season"].drop_duplicates().tolist()
    if prediction_data is not None and not prediction_data.empty:
        for season in prediction_data["season"].drop_duplicates():
            if season not in season_order:
                season_order.append(season)

    chart = alt.Chart(data).mark_line(point=not enable_collapse_values).encode(
        x=alt.X("season:N", title="Season", sort=season_order),
        y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
    )
    if not enable_collapse_values:
        chart = chart.encode(tooltip=tooltip)

    chart_layers = [chart]

    if enable_collapse_values and not data.empty:
        single_team_points = alt.Chart(data[data["team_count"].eq(1)]).mark_point().encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title=statistic_name, format=".2f"),
                alt.Tooltip("team_values:N", title="Values by team"),
            ],
        )
        multiple_team_points = alt.Chart(data[data["team_count"].gt(1)]).mark_point().encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title=f"Average {statistic_name}", format=".2f"),
                alt.Tooltip("team_values:N", title="Values by team"),
            ],
        )
        chart_layers.extend([single_team_points, multiple_team_points])

    if mean_value is not None:
        mean_data = pd.DataFrame({"mean": [mean_value]})
        mean_line = alt.Chart(mean_data).mark_rule(
            color="#8A8A8A",
            opacity=0.75,
            strokeDash=[6, 4],
            strokeWidth=1.5,
        ).encode(
            y=alt.Y("mean:Q", scale=y_scale),
            tooltip=[alt.Tooltip("mean:Q", title="Role average", format=".2f")],
        )
        chart_layers.append(mean_line)

    if prediction_data is not None and not prediction_data.empty:
        prediction_point = alt.Chart(prediction_data).mark_point(
            color="#BE27D9",
            filled=True,
            shape="diamond",
            size=150,
        ).encode(
            x=alt.X("season:N", title="Season", sort=season_order),
            y=alt.Y("value:Q", title=statistic_name, scale=y_scale),
            tooltip=[
                alt.Tooltip("season:N", title="Season"),
                alt.Tooltip("value:Q", title="AI prediction", format=".2f"),
            ],
        )
        chart_layers.append(prediction_point)

    return alt.layer(*chart_layers)


def compute_role_column_means(history_players: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    """Compute numeric column means by role, giving each player equal weight.

    First average each player's historical values, then average those results
    across all players with the same role.

    Params
    ----------
    history_players : pandas.DataFrame
        Historical player rows containing role and numeric statistics.

    Returns
    -------
    dict
        Statistic means indexed first by role and then by column.
    """
    numeric_columns = history_players.select_dtypes(include="number").columns
    role_column_means = {}

    for role in get_roles_dict().keys():
        # Keep all historical rows for players of the requested role.
        role_players = history_players.loc[
            history_players["fanta_role"] == role,
            ["player", *numeric_columns],
        ]

        # Average each player's history, then average all players of the role.
        player_column_means = role_players.groupby("player")[numeric_columns].mean()
        role_column_means[role] = {
            column: (
                None
                if player_column_means[column].dropna().empty
                else float(player_column_means[column].mean())
            )
            for column in numeric_columns
        }

    return role_column_means


def plot_comparison_between_players(history_players: pd.DataFrame, filtered_players: pd.DataFrame) -> None:
    """Compare the historical statistics of two selected players.

    The statistics configured for both player roles are combined and displayed
    in the same order. The first player is shown on the left and the second one
    on the right.

    Params
    ----------
    history_players : pandas.DataFrame
        Complete historical dataset used to calculate role averages.
    filtered_players : pandas.DataFrame
        DataFrame containing the historical records of two players.
    """
    role_column_means = compute_role_column_means(history_players)

    available_players = filtered_players["player"].dropna().drop_duplicates().tolist()
    selected_players = st.session_state.get("statistics_player_key", [])
    player_names = [player for player in selected_players if player in available_players]

    # Add players missing from Session State while preserving DataFrame order.
    for player in available_players:
        if player not in player_names:
            player_names.append(player)

    # Create the cols to plot as the union of the cols of the 2 players
    columns_to_plot = []
    for player_name in player_names:
        player_df = filtered_players[filtered_players["player"] == player_name]

        fanta_role = player_df["fanta_role"].dropna().iloc[0]
        role_name = get_roles_dict()[fanta_role]
        columns = st.session_state.get(f"settings_{fanta_role}_graphical_cols_key", [])

        for col in columns:
            if col in filtered_players.columns and col not in columns_to_plot:
                columns_to_plot.append(col)

    # Keep the same readable order in both player columns
    columns_to_plot = sorted(columns_to_plot, key=lambda col: get_user_view_of_column(col).lower())

    # Calculate the common Y-axis limits for each statistic.
    y_limits_dict = {}
    for col in columns_to_plot:
        player_min_values = []
        player_max_values = []

        for player_name in player_names:
            player_df = filtered_players[filtered_players["player"] == player_name]
            player_values = player_df[col]
            player_values = pd.to_numeric(player_values, errors="coerce").dropna()

            if not player_values.empty:
                player_min_values.append(float(player_values.min()))
                player_max_values.append(float(player_values.max()))

            player_role = player_df["fanta_role"].dropna().iloc[0]
            mean_value = role_column_means.get(player_role, {}).get(col)
            if mean_value is not None:
                player_min_values.append(mean_value)
                player_max_values.append(mean_value)

        if player_min_values and player_max_values:
            y_min = min(player_min_values)
            y_max = max(player_max_values)

            # Avoid an empty axis range when every value is the same.
            if y_min == y_max:
                padding = max(abs(y_min) * 0.05, 0.01)
                y_min -= padding
                y_max += padding

            y_limits_dict[col] = (y_min, y_max)

    col1, _, col2 = st.columns([9,1,9])
    player_columns = [col1, col2]

    for player_name, player_column in zip(player_names, player_columns):
        chart_df = filtered_players[filtered_players["player"] == player_name].copy()
        chart_df = chart_df.sort_values("season")

        for col in columns_to_plot:
            chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")

        with player_column:

            # Players header
            fanta_role = chart_df["fanta_role"].dropna().iloc[0]
            role_name = get_roles_dict()[fanta_role].capitalize()
            role_badge_color = get_color_per_role(role=fanta_role, color_version=False)
            latest_team = chart_df["team"].dropna().iloc[-1]
            with st.container(border=True):
                st.markdown(
                    f"### :material/person: {player_name}",
                    text_alignment="center",
                )
                st.markdown(
                    f":{role_badge_color}-badge[{role_name} ({fanta_role})]  \n:violet-badge[{latest_team}]",
                    text_alignment="center",
                )

            # Creation of the plots
            for col in columns_to_plot:
                data = chart_df[["season", "team", col]].dropna(subset=["season", col])
                data = data.rename(columns={col: "value"})
                data["team"] = data["team"].fillna("Unknown team")
                user_view_col = get_user_view_of_column(col)

                st.markdown(
                    f"<h4 style='text-align: center;'>{user_view_col}</h4>",
                    unsafe_allow_html=True
                )

                if data.empty:
                    st.info("No data available for this statistic.")
                    continue

                y_min, y_max = y_limits_dict[col]
                mean_value = role_column_means.get(fanta_role, {}).get(col)
                chart = create_player_history_chart(
                    data,
                    user_view_col,
                    (y_min, y_max),
                    mean_value,
                )

                st.altair_chart(
                    chart,
                    width="stretch",
                )
    return


def plot_player_history(
        history_players: pd.DataFrame,
        player: str,
        columns_to_plot=None,
        feature=None,
        seasons_to_plot=None,
        disable_player_name=False,
        enable_ai_predictions=True,
        models_packages_dict=None,
    ) -> None:
    """
    Display the selected historical statistics for a single player.

    Each chart represents the evolution of one statistic across the requested
    number of recent seasons.

    Params
    ----------
    history_players:
        DataFrame containing the historical records of the players.
    """
    role_column_means = compute_role_column_means(history_players)
    full_player_history = history_players[history_players["player"].eq(player)].copy()

    if full_player_history.empty:
        st.info(f"No history available for {player}.")
        return

    full_player_history = full_player_history.sort_values("season")
    player_history = full_player_history.copy()
    player_roles = player_history["fanta_role"].dropna()
    if player_roles.empty:
        st.info(f"No Fantacalcio role available for {player}.")
        return
    
    fanta_role = player_roles.iloc[-1]

    # A specific feature takes precedence over a list of columns.
    if isinstance(feature, str) and feature:
        requested_columns = [feature]
    elif columns_to_plot is not None:
        requested_columns = list(columns_to_plot)
    else:
        requested_columns = st.session_state.get(f"settings_{fanta_role}_graphical_cols_key", [])

    selected_columns = list(dict.fromkeys(
        column
        for column in requested_columns
        if isinstance(column, str) and column and column in player_history.columns
    ))

    # Case of no fields selected
    if not selected_columns:
        st.info("Select at least one statistic for this role in the Settings page.")
        return

    # Convert selected statistics to numeric values.
    for col in selected_columns:
        player_history[col] = pd.to_numeric(player_history[col], errors="coerce")

    # Player header
    player_name = player_history["player"].dropna().iloc[0]
    player_teams = player_history["team"].dropna()
    latest_team = player_teams.iloc[-1] if not player_teams.empty else "Unknown team"

    with st.container(border=True, key=f"dark-card-{player_name}{f'_{feature}' if feature is not None else ''}"):
        
        if not disable_player_name:
            cols = st.columns([21,34])
            with cols[0]:
                st.markdown(
                    f"{get_circular_role_icon(fanta_role, font_size=18, height=28, width=28, y_translation=14)}",
                    text_alignment="right",
                    anchors=False,
                    unsafe_allow_html=True
                )
            with cols[1]:
                st.markdown(
                    f"### {player_name}",
                    text_alignment="left",
                )
            st.markdown(
                f":violet-badge[{latest_team}]",
                text_alignment="center",
            )
            _, col, _ = st.columns([1,2,1])
            with col:
                set_player_card_background()
                with st.container(border=True, horizontal_alignment="center", width="stretch", key=f"dark-card-player-portrait-{player_name}_col1"):
                    st.image(get_player_img_url(player_name))
        
        st.space(20)

        # Create one graphic for every selected column.
        for column in selected_columns:
            data = player_history[["season", "team", column]].dropna(subset=["season", column])
            data = data.rename(columns={column: "value"})
            data["team"] = data["team"].fillna("Unknown team")

            prediction_data = None
            can_predict_column = (
                enable_ai_predictions
                and column.endswith("_per90")
                and column in features_to_predict_per_role_dict.get(fanta_role, [])
                and models_packages_dict is not None
                and column in models_packages_dict
            )
            if can_predict_column:
                available_seasons = history_players["season"].dropna().astype(str).sort_values()
                if not available_seasons.empty:
                    current_season = available_seasons.iloc[-1]
                    prediction_history = full_player_history[
                        full_player_history["season"].astype(str).ne(current_season)
                    ]
                    model_package = models_packages_dict[column]
                    model_input = build_temporal_player_input(
                        player_history=prediction_history,
                        features=model_package["features"],
                    )
                    if model_input.attrs["available_lags"] > 0:
                        prediction = max(0.0, float(predict(
                            model_package=model_package,
                            player_history=model_input,
                        )))
                        prediction_data = pd.DataFrame({
                            "season": [current_season],
                            "value": [prediction],
                        })

            # Keep the requested number of historical seasons. For predicted
            # features, the current season is added separately as an extra point.
            if prediction_data is not None:
                data = data[data["season"].astype(str).ne(current_season)]
            if seasons_to_plot is not None:
                recent_seasons = (
                    data["season"]
                    .drop_duplicates()
                    .sort_values()
                    .tail(int(seasons_to_plot))
                )
                data = data[data["season"].isin(recent_seasons)].sort_values("season")

            st.markdown(
                f"#### {get_user_view_of_column(column)}",
                text_alignment="center",
                anchors=False,
            )
            if data.empty and prediction_data is None:
                st.info("No data available for this statistic.")
                continue

            mean_value = role_column_means.get(fanta_role, {}).get(column)
            chart = create_player_history_chart(
                data,
                statistic_name=get_user_view_of_column(column),
                mean_value=mean_value,
                prediction_data=prediction_data,
                enable_collapse_values=True
            )
            st.altair_chart(
                chart,
                width="stretch",
            )
    return


def create_vertical_teams(
    fanta_manager_players_dict: dict,
    n_cols: int,
    page_name: str,
    enable_bought_players_stats_key: str,
    remove_player_callback,
):
    """Display multiple Fanta Manager teams in compact vertical columns.

    Params
    ----------
    fanta_manager_players_dict : dict
        Purchased-player DataFrames indexed by Fanta Manager.
    n_cols : int
        Number of team columns to display.
    page_name : str
        Page prefix used to build stable widget keys.
    enable_bought_players_stats_key : str
        Session key controlling compact role statistics.
    remove_player_callback : callable
        Callback invoked by each player removal button.
    """

    # Initializations
    my_fanta_manager = st.session_state["settings_my_manager_key"]
    fanta_managers = st.session_state.get("settings_managers_key", [])
    if not fanta_managers:
        return
    ordered_fanta_managers = fanta_manager_players_dict.keys()
    starting_budget = st.session_state.get("settings_budget_widget_key", 500)

    colors = {
        "orange": ("rgba(255,255,255,1)", "rgba(255,165,0,0.80)"),
        "green": ("rgba(255,255,255,1)", "rgba(0,128,0,0.80)"),
        "blue": ("rgba(255,255,255,1)", "rgba(0,0,255,0.80)"),
        "red": ("rgba(255,255,255,1)", "rgba(255,0,0,0.80)"),
        "dark_green": ("rgba(255,255,255,1)", "rgba(45,90,65,1.0)"),
        "gray": ("rgba(255,255,255,1)", "rgba(128,128,128,0.80)"),
    }

    # Iterations on fanta managers
    manager_cols = st.columns(n_cols)
    for col, fanta_manager in zip(manager_cols, ordered_fanta_managers):

        # Preparation of the bought dataframe
        bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
        if bought_players.empty:
            bought_players = pd.DataFrame(columns=["player", "role", "mln"])
        bought_players["mln"] = pd.to_numeric(bought_players["mln"], errors="coerce").fillna(1).astype(int)
        
        # Initializations
        tot_spent = bought_players["mln"].sum()
        available_budget = starting_budget - tot_spent
        role_budget_limits_dict = get_role_budget_limits()
        role_number_limits_dict = get_role_limits()
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"
        
        # Initialize variables for the available budget metric
        if last_transaction_amount_key not in st.session_state:
            if not bought_players.empty and "id" in bought_players.columns:
                last_bought_player = bought_players.iloc[-1]
                st.session_state[last_transaction_player_id_key] = str(last_bought_player["id"])
                st.session_state[last_transaction_amount_key] = -int(last_bought_player["mln"])
            else:
                st.session_state[last_transaction_player_id_key] = ""
                st.session_state[last_transaction_amount_key] = 0
        else:
            st.session_state.setdefault(last_transaction_amount_key, 0)
        
        # Prepare variables for the available budget metric
        budget_value_color = "green" if available_budget >= 0 else "red"
        budget_value = f"+{available_budget}" if available_budget >= 0 else f"-{available_budget}"
        last_transaction_amount = st.session_state[last_transaction_amount_key]
        if last_transaction_amount > 0:
            budget_delta = f"+{last_transaction_amount} mln"
            budget_delta_color = "green"
            budget_delta_arrow = "up"
        elif last_transaction_amount < 0:
            budget_delta = f"{last_transaction_amount} mln"
            budget_delta_color = "red"
            budget_delta_arrow = "down"
        else:
            budget_delta = None
            budget_delta_color = "gray"
            budget_delta_arrow = "off"

        # Compute the dictionary with the total mln spent per role
        tot_spent_per_role = {}
        for role, role_budget_limit in role_budget_limits_dict.items():
            bought_players_role = bought_players.loc[bought_players["role"] == role]
            tot_spent_per_role[role] = bought_players_role['mln'].sum()

        with col:

            st.markdown(
                f'### :color[{fanta_manager}]{{foreground="white"}}',
                text_alignment="left",
            )

            set_text_size(text_size=1.1, class_name="shrinked-team")
            with st.container(key=f"dark-card-{fanta_manager}-shrinked-team_vertical_teams", border=True, height="stretch", width="stretch"):
                    
                col1, col2 = st.columns([9,10])
                with col1:
                    try:
                        st.image(f"img/managers/{fanta_manager.lower()}.png", output_format="PNG")
                    except:
                        st.image("img/managers/unknown.png", output_format="PNG")
                with col2:
                    st.metric(
                        label="**Budget**",
                        value=f":{budget_value_color}[{budget_value} $]",
                        delta=budget_delta,
                        delta_color=budget_delta_color,
                        delta_arrow=budget_delta_arrow,
                        width="content",
                        height="content",
                        icon="💰"
                    )

                if bought_players.empty:
                    st.caption("No players purchased")
                    continue

                for i, role in enumerate(get_roles_dict()):
                    players_of_role = bought_players[bought_players["role"].eq(role)]
                    if players_of_role.empty:
                        continue

                    players_of_role = bought_players[bought_players["role"].eq(role)]

                    badge_color = get_color_per_role(role, color_version=False)
                    bought_number_foreground, bought_number_background = colors[badge_color]
                    budget_spent_foreground, budget_spent_background = colors["dark_green"]

                    # Cases of warinings
                    if players_of_role.shape[0] > role_number_limits_dict[role]:
                        warning_bought_number_background = "rgba(0,0,0,0.85)"
                        warning_bought_number_foreground = "rgba(255,75,75,1)"
                        warning_bought_number_icon = "⚠️"
                    else:
                        warning_bought_number_background = bought_number_background
                        warning_bought_number_foreground = bought_number_foreground
                        warning_bought_number_icon = ""

                    if tot_spent_per_role[role] > role_budget_limits_dict[role]:
                        warning_budget_spent_background = "rgba(0,0,0,0.85)"
                        warning_budget_spent_foreground = "rgba(255,75,75,1)"
                    else:
                        warning_budget_spent_background = budget_spent_background
                        warning_budget_spent_foreground = budget_spent_foreground

                    with st.container(border=True if not st.session_state[enable_bought_players_stats_key] else False):

                        # Case of view of the number of bought players per role enabled
                        if not st.session_state[enable_bought_players_stats_key]:

                            st.markdown(
                                f'{warning_bought_number_icon} :color[**{get_roles_dict()[role].capitalize()}s** '
                                f'{players_of_role.shape[0]}/{role_number_limits_dict[role]}]'
                                f'{{foreground="{warning_bought_number_foreground}" background="{warning_bought_number_background}"}}',
                                text_alignment="left",
                            )
  

                        for j, (_, player) in enumerate(players_of_role.iterrows()):
                            error_color = "red" if j+1 > role_number_limits_dict[role] else "white"

                            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns([1,5,2,2], vertical_alignment="center")
                            with sub_col1:
                                st.markdown(f"{get_circular_role_icon(role, font_size=13, height=21, width=21)}", unsafe_allow_html=True)
                            with sub_col2:
                                st.markdown(f':color[**{player["player"]}**]{{foreground="{error_color}"}}')
                            with sub_col3:
                                st.caption(f"{player['mln']}", text_alignment="right")
                            with sub_col4:
                                st.button(
                                    ":material/delete:",
                                    key=f"{page_name}_{fanta_manager}_{player['id']}_remove_player_key",
                                    help=f"Remove {player['player']} from {fanta_manager}.",
                                    type="tertiary",
                                    width="stretch",
                                    on_click=remove_player_callback,
                                    args=(player.to_dict(),),
                                )
                        
                        if not st.session_state[enable_bought_players_stats_key]:
                            if fanta_manager == my_fanta_manager:
                                budget_per_role_str = f"/{role_budget_limits_dict[role]}"
                            else:
                                budget_per_role_str = ""

                            st.markdown(
                                f'###### :color[Spent: {tot_spent_per_role[role]}{budget_per_role_str} mln]'
                                f'{{foreground="{warning_budget_spent_foreground}" background="{warning_budget_spent_background}"}}',
                                width="stretch",
                                text_alignment="left",
                            )
                    
                if available_budget < 0:
                    st.error("Budget exceeded")
            
    return



def create_horizontal_teams(
    fanta_manager_players_dict: dict,
    page_name: str,
    remove_player_callback,
):
    """Display Fanta Manager teams in full-width horizontal sections.

    Params
    ----------
    fanta_manager_players_dict : dict
        Purchased-player DataFrames indexed by Fanta Manager.
    page_name : str
        Page prefix used to build stable widget keys.
    remove_player_callback : callable
        Callback invoked by each player removal button.
    """

    # Initializations
    my_fanta_manager = st.session_state["settings_my_manager_key"]
    fanta_managers = st.session_state.get("settings_managers_key", [])
    if not fanta_managers:
        return
    ordered_fanta_managers = fanta_manager_players_dict.keys()
    starting_budget = st.session_state.get("settings_budget_widget_key", 500)

    colors = {
        "orange": ("rgba(255,255,255,1)", "rgba(255,165,0,0.80)"),
        "green": ("rgba(255,255,255,1)", "rgba(0,128,0,0.80)"),
        "blue": ("rgba(255,255,255,1)", "rgba(0,0,255,0.80)"),
        "red": ("rgba(255,255,255,1)", "rgba(255,0,0,0.80)"),
        "dark_green": ("rgba(255,255,255,1)", "rgba(45,90,65,1.0)"),
        "gray": ("rgba(255,255,255,1)", "rgba(128,128,128,0.80)"),
    }

    # Iterations on fanta managers
    for fanta_manager in ordered_fanta_managers:

        # Preparation of the bought dataframe
        bought_players = fanta_manager_players_dict.get(fanta_manager, pd.DataFrame()).copy()
        if bought_players.empty:
            bought_players = pd.DataFrame(columns=["player", "role", "mln"])
        bought_players["mln"] = pd.to_numeric(bought_players["mln"], errors="coerce").fillna(1).astype(int)
        
        # Initializations
        tot_spent = bought_players["mln"].sum()
        available_budget = starting_budget - tot_spent
        role_budget_limits_dict = get_role_budget_limits()
        role_number_limits_dict = get_role_limits()
        last_transaction_amount_key = f"{page_name}_{fanta_manager}_last_transaction_amount_key"
        last_transaction_player_id_key = f"{page_name}_{fanta_manager}_last_transaction_player_id_key"
        
        # Initialize variables for the available budget metric
        if last_transaction_amount_key not in st.session_state:
            if not bought_players.empty and "id" in bought_players.columns:
                last_bought_player = bought_players.iloc[-1]
                st.session_state[last_transaction_player_id_key] = str(last_bought_player["id"])
                st.session_state[last_transaction_amount_key] = -int(last_bought_player["mln"])
            else:
                st.session_state[last_transaction_player_id_key] = ""
                st.session_state[last_transaction_amount_key] = 0
        else:
            st.session_state.setdefault(last_transaction_amount_key, 0)
        
        # Prepare variables for the available budget metric
        budget_value_color = "green" if available_budget >= 0 else "red"
        budget_value = f"+{available_budget}" if available_budget >= 0 else f"-{available_budget}"
        last_transaction_amount = st.session_state[last_transaction_amount_key]
        if last_transaction_amount > 0:
            budget_delta = f"+{last_transaction_amount} mln"
            budget_delta_color = "green"
            budget_delta_arrow = "up"
        elif last_transaction_amount < 0:
            budget_delta = f"{last_transaction_amount} mln"
            budget_delta_color = "red"
            budget_delta_arrow = "down"
        else:
            budget_delta = "0 mln"
            budget_delta_color = "gray"
            budget_delta_arrow = "off"

        # Compute the dictionary with the total mln spent per role
        tot_spent_per_role = {}
        for role, role_budget_limit in role_budget_limits_dict.items():
            bought_players_role = bought_players.loc[bought_players["role"] == role]
            tot_spent_per_role[role] = bought_players_role['mln'].sum()
        
        st.markdown(
            f'### :color[{fanta_manager}]{{foreground="rgba(255,255,255,1)"}}',
            text_alignment="left",
        )

        with st.container(key=f"dark-card-{fanta_manager}_vertical_teams", height="stretch", width="stretch"):

            col_fanta_manager, col_players = st.columns([1,7])
            with col_fanta_manager:

                set_text_size(text_size=1.1, class_name="shrinked-team")
                with st.container(key=f"{fanta_manager}-shrinked-team", height="stretch", width="stretch"):
                    try:
                        st.image(f"img/managers/{fanta_manager.lower()}.png", output_format="PNG")
                    except:
                        st.image("img/managers/unknown.png", output_format="PNG")

                    with st.container(border=True):
                        st.metric(
                            label="**Budget**",
                            value=f":{budget_value_color}[{budget_value} $]",
                            delta=budget_delta,
                            delta_color=budget_delta_color,
                            delta_arrow=budget_delta_arrow,
                            width="stretch",
                            height="stretch",
                            icon="💰"
                        )
            
            with col_players:

                for i, (role, col) in enumerate(zip(get_roles_dict(), st.columns(len(get_roles_dict().keys()), border=True))):
                    players_of_role = bought_players[bought_players["role"].eq(role)]

                    badge_color = get_color_per_role(role, color_version=False)
                    bought_number_foreground, bought_number_background = colors[badge_color]
                    budget_spent_foreground, budget_spent_background = colors["dark_green"]

                    # Cases of warinings
                    if players_of_role.shape[0] > role_number_limits_dict[role]:
                        warning_bought_number_background = "rgba(0,0,0,0.85)"
                        warning_bought_number_foreground = "rgba(255,75,75,1)"
                        warning_bought_number_icon = "⚠️"
                    else:
                        warning_bought_number_background = bought_number_background
                        warning_bought_number_foreground = bought_number_foreground
                        warning_bought_number_icon = ""

                    if tot_spent_per_role[role] > role_budget_limits_dict[role]:
                        warning_budget_spent_background = "rgba(0,0,0,0.85)"
                        warning_budget_spent_foreground = "rgba(255,75,75,1)"
                    else:
                        warning_budget_spent_background = budget_spent_background
                        warning_budget_spent_foreground = budget_spent_foreground

                    with col:
                            
                        st.markdown(
                            f'###### {warning_bought_number_icon} :color[**{get_roles_dict()[role].capitalize()}s** '
                            f'{players_of_role.shape[0]}/{role_number_limits_dict[role]}]'
                            f'{{foreground="{warning_bought_number_foreground}" background="{warning_bought_number_background}"}}',
                            text_alignment="center",
                        )

                        if players_of_role.empty:
                            st.caption(f"No {get_roles_dict()[role].capitalize()}s purchased")
                            continue

                        for j, (_, player) in enumerate(players_of_role.iterrows()):

                            sub_col1, sub_col2, sub_col3, sub_col4 = st.columns([1,5,2,2], vertical_alignment="center")
                            with sub_col1:
                                st.markdown(f"{get_circular_role_icon(role, font_size=13, height=21, width=21)}", unsafe_allow_html=True)
                            with sub_col2:
                                error_color = "red" if j+1 > role_number_limits_dict[role] else "white"
                                st.markdown(
                                    f':color[**{player["player"]}**]'
                                    f'{{foreground="{error_color}"}}'
                                )
                            with sub_col3:
                                st.caption(f"{player['mln']}", text_alignment="right")
                            with sub_col4:
                                st.button(
                                    ":material/delete:",
                                    key=f"{page_name}_{fanta_manager}_{player['id']}_remove_player_key",
                                    help=f"Remove {player['player']} from {fanta_manager}.",
                                    type="tertiary",
                                    width="stretch",
                                    on_click=remove_player_callback,
                                    args=(player.to_dict(),),
                                )

                        with st.container(height="stretch", width="stretch", vertical_alignment="bottom"):
                            if fanta_manager == my_fanta_manager:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]}/{role_budget_limits_dict[role]} mln]'
                                    f'{{foreground="{warning_budget_spent_foreground}" background="{warning_budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="center",
                                )
                            else:
                                st.markdown(
                                    f'###### :color[Spent: {tot_spent_per_role[role]} mln]'
                                    f'{{foreground="{warning_budget_spent_foreground}" background="{warning_budget_spent_background}"}}',
                                    width="stretch",
                                    text_alignment="center",
                                )
                        
                    if available_budget < 0:
                        st.error("Budget exceeded")
                
    return
