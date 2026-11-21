from pathlib import Path
from typing import Optional

from app.models import Dataset

DATA_DIR_CANDIDATES = [
    Path("data").resolve(),
    Path("../data").resolve(),
    Path("/app/data"),
    Path(__file__).resolve().parents[3] / "data",
]


def get_rules_path_for_dataset(dataset: Dataset) -> Optional[Path]:
    """Finds YAML quality rules for dataset based on its name or original_filename."""
    name_str = f"{dataset.name} {dataset.original_filename}".lower()
    rule_filename = None
    if "payroll" in name_str:
        rule_filename = "payroll_rules.yaml"
    elif "customer" in name_str:
        rule_filename = "customers_rules.yaml"

    if not rule_filename:
        return None

    for candidate in DATA_DIR_CANDIDATES:
        rule_path = candidate / rule_filename
        if rule_path.exists() and rule_path.is_file():
            return rule_path

    return None
