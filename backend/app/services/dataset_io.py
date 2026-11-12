"""File I/O helpers shared by profiling, quality and anonymisation endpoints."""

from __future__ import annotations

import io
import json

import pandas as pd

from app.models import Dataset


def load_dataframe_for_dataset(
    dataset: Dataset,
    dtype_columns: dict[str, object] | None = None,
) -> pd.DataFrame:
    """Read a stored dataset file back into a DataFrame.

    ``dtype_columns`` keeps identifier-like columns (for example IPN) as text
    so anonymisation never changes their original representation.
    """
    with open(dataset.file_path, "rb") as fh:
        content = fh.read()

    file_type = dataset.file_type.lower()
    if file_type == "csv":
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "cp1251", "latin1"):
            try:
                return pd.read_csv(
                    io.BytesIO(content),
                    encoding=encoding,
                    dtype=dtype_columns or None,
                )
            except Exception as exc:  # try the next encoding
                last_error = exc
        raise ValueError(f"Cannot decode CSV file: {last_error}")
    if file_type == "json":
        data = json.loads(content.decode("utf-8"))
        frame = pd.DataFrame(data)
        if dtype_columns:
            for column, dtype in dtype_columns.items():
                if column in frame.columns:
                    frame[column] = frame[column].astype(dtype)
        return frame
    raise ValueError(f"Unsupported file type: {file_type}")


__all__ = ["load_dataframe_for_dataset"]
