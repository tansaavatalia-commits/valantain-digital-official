"""Configurazione del pilota automatico (autopilot.yaml)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class EtsyConfig(BaseModel):
    enabled: bool = True
    mode: Literal["active", "draft"] = "active"
    max_new_listings_per_run: int = Field(10, ge=0, le=100)
    language: str = "en"
    taxonomy_name: str = "Calendars & Planners"
    quantity: int = Field(999, ge=1)


class IdeasConfig(BaseModel):
    enabled: bool = True
    lines_per_run: int = Field(1, ge=0, le=5)
    max_auto_lines: int = Field(40, ge=0)


class Config(BaseModel):
    etsy: EtsyConfig = Field(default_factory=EtsyConfig)
    ideas: IdeasConfig = Field(default_factory=IdeasConfig)
    copy_engine: Literal["claude", "template"] = "template"


def load_config(path: str | Path = "autopilot.yaml") -> Config:
    p = Path(path)
    return Config.model_validate(yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {})
