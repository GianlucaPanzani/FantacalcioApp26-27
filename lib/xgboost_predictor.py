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
        """
        XGBoost predictor per fantacalcio.

        Parameters
        ----------
        player_col : str
            Nome colonna giocatore.
        season_col : str
            Nome colonna stagione.
        target_col : str
            Variabile da predire.
        window_size : int
            Numero di stagioni precedenti utilizzate come input.
        drop_cols : list
            Colonne da eliminare dalle feature.
        param_grid : dict
            Griglia per GridSearchCV.
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
        """
        Build temporal examples like: [T-window_size+1, T-window_size ... T-1, T]
        ---> to predict the target season T+1
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
        """ Split without shuffle. The temporal sequence is maintained. """
        split = int(len(X) * split_ratio)
        return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]

    def train(self, X_train, y_train, verbose=1):
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
        if self.model is None:
            raise Exception("Model not trained")
        return self.model.predict(X)



    def evaluate(self, X_test, y_test):
        pred = self.predict(X_test)
        results = {
            "MAE": mean_absolute_error(y_test, pred),
            "RMSE": np.sqrt(mean_squared_error(y_test, pred)),
            "R2": r2_score(y_test, pred)
        }
        return results

    def save(self, path):
        joblib.dump(self.model, path)

    def load(self, path):
        self.model = joblib.load(path)




def prepare_player_input(
    player_history,
    features,
    window_size=4
):

    player_history = player_history.sort_values("season").tail(window_size)

    input_dict = {}
    for i, (_, row) in enumerate(player_history.iterrows()):
        t = window_size - i
        for col in player_history.columns:
            if col in ["player", "season"]:
                continue
            input_dict[f"{col}_t-{t}"] = row[col]


    X = pd.DataFrame([input_dict])

    return X[features]