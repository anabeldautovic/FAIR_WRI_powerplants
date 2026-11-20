"""Stage 1 - Ingest: read the WRI CSV into a pandas table.

Every column is read as text (dtype=str) and empty cells stay as "" instead
of NaN, so that the clean stage decides explicitly what each value means.
"""

import pandas as pd

from . import config


def ingest(limit=None):
    if not config.RAW_CSV.exists():
        raise SystemExit(
            f"Source CSV not found: {config.RAW_CSV}\n"
            f"Download WRI GPPD v1.3.0 from {config.RAW_CSV_URL} and unzip it into data/raw/."
        )
    df = pd.read_csv(config.RAW_CSV, dtype=str, keep_default_na=False,
                     encoding="utf-8", nrows=limit)
    return df
