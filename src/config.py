from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass
class Paths:
    bronze: Path
    silver: Path
    gold: Path
    quarantine: Path
    warehouse: Path
    reports: Path
    logs: Path
    sql: Path
    workbook: Path


@dataclass
class Config:
    sheets: list[str]
    required_columns: dict[str, list[str]]
    paths: Paths
    date_start: str
    date_end: str
    red_eye_start_hour: int
    red_eye_end_hour: int
    max_duration_hours: int
    age_bands: list[tuple[int, int, str]]
    pepper_env_var: str
    token_hex_length: int
    raw: dict = field(repr=False, default_factory=dict)

    def age_band(self, age: int) -> str:
        for lo, hi, label in self.age_bands:
            if lo <= age <= hi:
                return label
        return "unknown"

    def pepper(self) -> str:
        value = os.environ.get(self.pepper_env_var)
        if not value:
            raise RuntimeError(
                f"{self.pepper_env_var} is not set. Copy .env.example to .env and set a value."
            )
        return value


def load_config(path: str | Path = ROOT / "config" / "pipeline.yaml") -> Config:
    _load_dotenv(ROOT / ".env")
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    p = raw["paths"]
    paths = Paths(
        bronze=ROOT / p["bronze"],
        silver=ROOT / p["silver"],
        gold=ROOT / p["gold"],
        quarantine=ROOT / p["quarantine"],
        warehouse=ROOT / p["warehouse"],
        reports=ROOT / p["reports"],
        logs=ROOT / p["logs"],
        sql=ROOT / p["sql"],
        workbook=ROOT / raw["source"]["workbook"],
    )
    rules = raw["business_rules"]
    age_bands = [(lo, hi, label) for lo, hi, label in rules["age_bands"]]

    return Config(
        sheets=raw["source"]["sheets"],
        required_columns=raw["source"]["required_columns"],
        paths=paths,
        date_start=raw["date_dim"]["start"],
        date_end=raw["date_dim"]["end"],
        red_eye_start_hour=rules["red_eye_start_hour"],
        red_eye_end_hour=rules["red_eye_end_hour"],
        max_duration_hours=rules["max_duration_hours"],
        age_bands=age_bands,
        pepper_env_var=raw["pii"]["pepper_env_var"],
        token_hex_length=raw["pii"]["token_hex_length"],
        raw=raw,
    )
