from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent.parent / "config" / "validation_rules.yaml"


@dataclass
class RuleResult:
    name: str
    table: str
    column: str
    severity: str
    total: int
    failed: int

    @property
    def passed(self) -> int:
        return self.total - self.failed


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]


def _pass_mask(series: pd.Series, rule: dict) -> pd.Series:
    rtype = rule["type"]
    params = rule.get("params", {})

    if rtype == "not_null":
        return series.notna()
    if rtype == "regex":
        matches = series.astype(str).str.match(params["pattern"])
        return series.isna() | matches
    if rtype == "in_set":
        allowed = set(params["values"])
        return series.isna() | series.isin(allowed)
    if rtype == "range":
        numeric = pd.to_numeric(series, errors="coerce")
        return series.isna() | numeric.between(params["min"], params["max"])
    if rtype == "unique":
        return ~series.duplicated(keep=False)
    if rtype == "referential":
        raise ValueError("referential rules are resolved by validate(), not _pass_mask")
    raise ValueError(f"unknown rule type: {rtype}")


def validate(
    tables: dict[str, pd.DataFrame], rules: list[dict] | None = None
) -> tuple[dict[str, pd.DataFrame], list[RuleResult]]:
    rules = rules if rules is not None else load_rules()
    flagged = {name: df.copy() for name, df in tables.items()}
    results: list[RuleResult] = []

    for rule in rules:
        table, column, name, severity = rule["table"], rule["column"], rule["name"], rule["severity"]
        df = flagged[table]

        if rule["type"] == "referential":
            ref_table, ref_column = rule["params"]["ref_table"], rule["params"]["ref_column"]
            ref_values = set(flagged[ref_table][ref_column].dropna())
            mask_pass = df[column].isna() | df[column].isin(ref_values)
        else:
            mask_pass = _pass_mask(df[column], rule)

        flag_col = f"_flag_{name}"
        df[flag_col] = ~mask_pass
        failed = int(df[flag_col].sum())
        results.append(RuleResult(name, table, column, severity, len(df), failed))
        logger.info(
            "rule %-32s [%s] %5d/%5d failed on %s.%s",
            name, severity, failed, len(df), table, column,
        )

    for table, df in flagged.items():
        error_cols = [
            f"_flag_{r.name}" for r in results if r.table == table and r.severity == "error"
        ]
        warning_cols = [
            f"_flag_{r.name}" for r in results if r.table == table and r.severity == "warning"
        ]
        df["_validation_error"] = df[error_cols].any(axis=1) if error_cols else False
        df["_validation_warning"] = df[warning_cols].any(axis=1) if warning_cols else False

    return flagged, results


def write_summary(results: list[RuleResult], path: Path) -> None:
    lines = ["# Validation rule summary", "", "| rule | table.column | severity | failed | total |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| {r.name} | {r.table}.{r.column} | {r.severity} | {r.failed} | {r.total} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
