"""The issues log: every odd value goes here instead of being guessed."""

import csv
from collections import Counter
from pathlib import Path


class IssueLog:
    """Collects (row id, column, value, problem) rows and writes them to a CSV."""

    FIELDS = ["row_id", "column", "value", "problem"]

    def __init__(self):
        self.rows = []

    def add(self, row_id, column, value, problem):
        self.rows.append({"row_id": row_id, "column": column,
                          "value": value, "problem": problem})

    def write(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=self.FIELDS)
            w.writeheader()
            w.writerows(self.rows)

    def summary(self):
        return Counter(r["problem"] for r in self.rows).most_common()
