import numpy as np
import pandas as pd
from xgboost import XGBRegressor
import joblib
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)


features_to_predict_per_role_dict: dict = {
    "P": [
        "clean_sheets_per90",
        "goals_against_per90",
    ],
    "D": [
        "goals_per90",
        "assists_per90",
        "tackles_won_per90",
    ],
    "C": [
        "goals_per90",
        "assists_per90",
    ],
    "A": [
        "goals_per90",
        "assists_per90",
    ],
}


features_to_predict_list = [
    "assists_per90",
    "clean_sheets_per90",
    "goals_against_per90",
    "goals_per90",
    "minutes",
    "tackles_won_per90",
]

features_per_season_per_match = {
    "assists_per90": " per season",
    "clean_sheets_per90": " per season",
    "goals_against_per90": " per season",
    "goals_per90": " per season",
    "minutes": " per match",
    "tackles_won_per90": " per match",
}



class XGBPlayerPerformancePredictor:

    def __init__(
        self,
        player_col="player",
        season_col="season",
        target_col="goals",
        window_size=3,
        drop_cols=None,
        param_grid=None,
        scoring="neg_mean_squared_error",
        cv=3
    ):
        """Initialize a temporal XGBoost predictor.

        Params
        ----------
        player_col : str
            Column containing player names.
        season_col : str
            Column containing season labels.
        target_col : str
            Target variable to predict.
        window_size : int
            Number of previous seasons used as model input.
        drop_cols : list or None
            Columns excluded from model features.
        param_grid : dict or None
            Hyperparameter grid used by ``GridSearchCV``.
        scoring : str
            Scikit-learn score used to select the best model.
        cv : int
            Number of cross-validation folds.
        """

        self.player_col = player_col
        self.season_col = season_col
        self.target_col = target_col
        self.window_size = window_size

        self.drop_cols = drop_cols if drop_cols else []

        self.param_grid = param_grid if param_grid else {
            "n_estimators": [100, 300],
            "max_depth": [3, 5, 7],
            "learning_rate": [0.01, 0.05, 0.1],
            "subsample": [0.8, 1.0],
            "colsample_bytree": [0.8, 1.0]
        }

        self.scoring = scoring
        self.cv = cv

        self.model = None
        self.columns = None
        return

    def build_temporal_dataset(self, df: pd.DataFrame):
        """Build temporal feature rows that predict the following season.

        Params
        ----------
        df : pandas.DataFrame
            Player history ordered internally by player and season.

        Returns
        -------
        tuple of pandas.DataFrame and pandas.Series
            Temporal model inputs and their target values.
        """
        X = []
        y = []

        df = df.sort_values([self.player_col, self.season_col])
        for player, player_df in df.groupby(self.player_col):
            # Sorted by season from the oldest to the most recent
            player_df = player_df.sort_values(self.season_col)

            # Scan from season_0 to season_N-windows_size
            for i in range(len(player_df) - self.window_size):
                # Number of rows = windows_size
                past = player_df.iloc[i:i+self.window_size]
                # Row to be predicted
                future = player_df.iloc[i+self.window_size]

                # Features of previous seasons
                new_row = {}
                for j in range(self.window_size):
                    row = past.iloc[j]
                    for col in player_df.columns:
                        if col in [self.player_col, self.season_col, self.target_col]:
                            continue
                        new_row[f"{col}_t-{self.window_size-j}"] = row[col]
                    
                target = future[self.target_col]

                # Append a row with windows_size * len(df.columns) elements
                X.append(new_row)
                y.append(target)

        X = pd.DataFrame(X)
        y = pd.Series(y)

        self.columns = X.columns.tolist()
        return X, y

    def temporal_split(self, X, y, split_ratio=0.8):
        """Split features and targets without changing temporal order.

        Params
        ----------
        X : pandas.DataFrame
            Temporal feature rows.
        y : pandas.Series
            Target values aligned with ``X``.
        split_ratio : float
            Fraction assigned to the training split.

        Returns
        -------
        tuple
            Training features, test features, training targets and test targets.
        """
        split = int(len(X) * split_ratio)
        return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]

    def train(self, X_train, y_train, verbose=1):
        """Tune and train the XGBoost regressor on temporal examples."""
        base_model = XGBRegressor(objective="reg:squarederror", random_state=42)

        grid = GridSearchCV(
            estimator=base_model,
            param_grid=self.param_grid,
            scoring=self.scoring,
            cv=self.cv,
            n_jobs=-1,
            verbose=verbose
        )

        grid.fit(X_train, y_train)
        self.model = grid.best_estimator_

        print(f"Best parameters: {grid.best_params_}")
        return

    def predict(self, X):
        """Predict target values with the trained estimator."""
        if self.model is None:
            raise Exception("Model not trained")
        return self.model.predict(X)



    def evaluate(self, X_test, y_test):
        """Return MAE, RMSE and R² metrics for a test dataset."""
        pred = self.predict(X_test)
        results = {
            "MAE": mean_absolute_error(y_test, pred),
            "RMSE": np.sqrt(mean_squared_error(y_test, pred)),
            "R2": r2_score(y_test, pred)
        }
        return results

    def save(self, path):
        """Serialize the trained estimator to disk with joblib."""
        joblib.dump(self.model, path)

    def load(self, path):
        """Load a serialized estimator from disk into this predictor."""
        self.model = joblib.load(path)




def build_temporal_player_input(
    player_history: pd.DataFrame,
    features: list[str],
    season_col: str = "season",
) -> pd.DataFrame:
    """Build the latest temporal row expected by a trained model.

    The window size is inferred from the feature suffixes stored with the model.
    Available historical lags are populated from newest to oldest; older missing
    lags remain zero so the input keeps the complete schema expected by XGBoost.

    Params
    ----------
    player_history : pandas.DataFrame
        Historical rows for one player.
    features : list of str
        Temporal feature names expected by the trained model.
    season_col : str
        Column used to order historical rows.

    Returns
    -------
    pandas.DataFrame
        One-row model input with metadata describing available history.
    """
    parsed_features = []
    invalid_features = []
    for feature in features:
        source_col, separator, lag_text = feature.rpartition("_t-")
        if not separator or not source_col or not lag_text.isdigit() or int(lag_text) < 1:
            invalid_features.append(feature)
            continue
        parsed_features.append((feature, source_col, int(lag_text)))

    required_lags = {lag for _, _, lag in parsed_features}
    window_size = max(required_lags, default=0)
    latest_history = player_history.sort_values(season_col).tail(window_size)
    available_lags = len(latest_history)

    input_row = {}
    available_features = []
    seasons_by_lag = {}
    for feature, source_col, lag in parsed_features:
        if lag > available_lags:
            input_row[feature] = 0.0
            continue

        history_row = latest_history.iloc[-lag]
        input_row[feature] = history_row[source_col]
        available_features.append(feature)
        seasons_by_lag[lag] = history_row[season_col]

    model_input = pd.DataFrame([input_row], columns=features)
    model_input = model_input.apply(pd.to_numeric, errors="coerce").fillna(0.0)
    model_input.attrs.update(
        {
            "available_features": available_features,
            "available_lags": available_lags,
            "required_lags": window_size,
            "seasons_by_lag": seasons_by_lag,
        }
    )

    return model_input



def get_team_impact_score(teams_history: pd.DataFrame, team: str, seasons: int = 3) -> float:
    """Calculate a team's recent strength relative to the league.

    The score combines:
    - results: 40%
    - goals scored per match: 30%
    - goals conceded per match: 30%

    Each component is ranked within its season from -1 to 1.
    Recent seasons receive progressively greater weight.

    Params
    ----------
    teams_history : pandas.DataFrame
        Team results and scoring statistics by season.
    team : str
        Team whose recent impact should be calculated.
    seasons : int
        Number of recent seasons included in the weighted score.

    Returns
    -------
    float
        Value between -1 and 1, or zero when no team history exists.
    """
    def season_rank(data, column: str, ascending: bool) -> pd.Series:
        """Scale within-season ranks for one metric to the range -1 to 1."""
        grouped = data.groupby("season")[column]
        ranks = grouped.rank(method="average", ascending=ascending)
        counts = grouped.transform("count")
        scores = 2 * (ranks - 1) / (counts - 1).replace(0, 1) - 1
        return scores.where(counts > 1, 0.0)

    numeric_columns = teams_history.select_dtypes(include="number").columns
    required_columns = ["team", "season", *numeric_columns]
    missing_columns = set(required_columns) - set(teams_history.columns)

    if missing_columns:
        raise ValueError(f"Missing columns: {sorted(missing_columns)}")

    data = teams_history[required_columns].copy()
    data[numeric_columns] = data[numeric_columns].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=numeric_columns)

    data["points_per_match"] = data["points"] / data["matches"]

    data["points_score"] = season_rank(data, "points_per_match", True)
    data["attack_score"] = season_rank(data, "goals_per90", True)
    data["defence_score"] = season_rank(data, "goals_against_per90", False)

    data["team_score"] = (
        0.40 * data["points_score"]
        + 0.30 * data["attack_score"]
        + 0.30 * data["defence_score"]
    )

    team_history = data[data["team"] == team].sort_values("season").tail(seasons)

    if team_history.empty:
        return 0.0

    scores = team_history["team_score"].tolist()
    weights = list(range(1, len(scores) + 1))
    weighted_score = sum(score * weight for score, weight in zip(scores, weights)) / sum(weights)

    return max(-1.0, min(1.0, weighted_score))


def predict(model_package: dict, player_history: pd.DataFrame) -> str:
    """Predict one feature using a model package and prepared player history.

    Params
    ----------
    model_package : dict
        Package containing a trained model and its ordered feature names.
    player_history : pandas.DataFrame
        Prepared temporal input containing the requested model features.

    Returns
    -------
    float
        Model prediction for the first input row.
    """

    features = model_package["features"]
    model = model_package["model"]

    # Prediction with XGBoost
    X_input = player_history.loc[:, features].iloc[[0]]
    prediction = model.predict(X_input)[0]

    return prediction


def get_transformed_feature_and_value(feature: str, pred_value, pred_minutes=None):
    """Convert a raw prediction into the label and unit shown in the UI.

    Params
    ----------
    feature : str
        Predicted model feature.
    pred_value : float
        Raw model prediction.
    pred_minutes : float or None
        Predicted minutes required to transform per-90 values.

    Returns
    -------
    tuple of str and float
        Readable feature label and transformed prediction.
    """
    
    def transform_feature(s: str):
        """Remove the per-90 suffix and format a readable feature label."""
        strings = s.split("_")[:-1]
        return " ".join([strings[0].capitalize()] + strings[1:])
    
    def transform_value_per90(v):
        """Convert a non-negative per-90 prediction into a season value."""
        if v < 0:
            return 0
        if pred_minutes is None:
            raise ValueError("Minutes is needed if the feture ends with \"_per90\".")
        return round(v * 38, 2)

    pred_value = float(pred_value)
    if feature.endswith("_per90"):
        return str(transform_feature(feature) + features_per_season_per_match[feature]), transform_value_per90(pred_value)
    if feature == "minutes":
        return str(feature.capitalize() + features_per_season_per_match["minutes"]), round(pred_value/90, 2)
    else:
        raise ValueError(f"The model is not able to predict the feature \"{feature}\".")
