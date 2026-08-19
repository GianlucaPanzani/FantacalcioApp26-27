import pandas as pd


def print_unique_values(df, max_values=30, show_counts=False):
    """
    Print a readable summary of the distinct values in every DataFrame column.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataset to inspect.
    max_values : int or None, default=30
        Maximum number of distinct values displayed per column.
        Use None to display every distinct value.
    show_counts : bool, default=False
        If True, also display the frequency of each value.
    """
    print(f"\nDataset shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print("=" * 80)

    for index, column in enumerate(df.columns, start=1):
        series = df[column]
        unique_count = series.nunique(dropna=False)
        missing_count = series.isna().sum()

        print(f"\n[{index}/{len(df.columns)}] {column}")
        print("-" * 80)
        print(
            f"Type: {series.dtype} | "
            f"Unique: {unique_count:,} | "
            f"Missing: {missing_count:,}"
        )

        if show_counts:
            values = series.value_counts(dropna=False)
        else:
            values = pd.Series(series.unique(), name="value")

        if max_values is not None and len(values) > max_values:
            displayed = values.head(max_values)
            truncated = True
        else:
            displayed = values
            truncated = False

        if show_counts:
            for value, count in displayed.items():
                print(f"  • {value!r}: {count:,}")
        else:
            for value in displayed:
                print(f"  • {value!r}")

        if truncated:
            remaining = len(values) - max_values
            print(f"  ... {remaining:,} additional values not displayed")

    print("\n" + "=" * 80)