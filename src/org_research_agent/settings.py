"""Load private settings from a git-ignored TOML file.

Client-specific criteria and prompts live outside the repository. This module
reads them and refuses to run if the file is missing, malformed, or still
contains placeholder values.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path("config/settings.private.toml")
PLACEHOLDER = "REPLACE_IN_PRIVATE_FILE"


class SettingsError(Exception):
    """Raised when the settings file cannot be used."""


@dataclass(frozen=True)
class AreaSettings:
    suburbs: tuple[str, ...]
    radius_km: float
    min_organisations: int


@dataclass(frozen=True)
class FitSettings:
    types: tuple[str, ...]
    min_staff: int


@dataclass(frozen=True)
class PromptSettings:
    research: str


@dataclass(frozen=True)
class Settings:
    area: AreaSettings
    fit: FitSettings
    prompts: PromptSettings


def _section(data: dict, name: str) -> dict:
    section = data.get(name)
    if not isinstance(section, dict):
        raise SettingsError(f"Missing [{name}] section in settings file.")
    return section


def _value(section: dict, section_name: str, key: str):
    if key not in section:
        raise SettingsError(f"Missing '{key}' in [{section_name}].")
    return section[key]


def _string_list(section: dict, section_name: str, key: str) -> tuple[str, ...]:
    value = _value(section, section_name, key)
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item.strip() for item in value)
    ):
        raise SettingsError(f"'{key}' in [{section_name}] must be a non-empty list of strings.")
    return tuple(item.strip() for item in value)


def _positive_number(section: dict, section_name: str, key: str) -> float:
    value = _value(section, section_name, key)
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise SettingsError(f"'{key}' in [{section_name}] must be a positive number.")
    return value


def load_settings(path: Path | str = DEFAULT_SETTINGS_PATH) -> Settings:
    """Read and validate the private settings file."""
    path = Path(path)
    if not path.is_file():
        raise SettingsError(
            f"Settings file not found: {path}. "
            "Copy config/settings.example.toml to config/settings.private.toml and edit it."
        )

    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise SettingsError(f"Settings file is not valid TOML: {error}") from error

    area = _section(data, "area")
    fit = _section(data, "fit")
    prompts = _section(data, "prompts")

    research = _value(prompts, "prompts", "research")
    if not isinstance(research, str) or not research.strip() or research == PLACEHOLDER:
        raise SettingsError("'research' in [prompts] is empty or still a placeholder.")

    return Settings(
        area=AreaSettings(
            suburbs=_string_list(area, "area", "suburbs"),
            radius_km=_positive_number(area, "area", "radius_km"),
            min_organisations=int(_positive_number(area, "area", "min_organisations")),
        ),
        fit=FitSettings(
            types=_string_list(fit, "fit", "types"),
            min_staff=int(_positive_number(fit, "fit", "min_staff")),
        ),
        prompts=PromptSettings(research=research),
    )
