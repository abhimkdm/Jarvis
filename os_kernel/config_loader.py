"""
Loads shared config.yaml and merges an LLM profile (local / deployed).
Default behavior: prefer deployed when environment is auto/deployed, but fall
back to local when the deployed endpoint is unreachable.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import requests
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAIN_CONFIG = PROJECT_ROOT / "config.yaml"
VALID_ENVIRONMENTS = frozenset({"local", "deployed", "auto"})


def _read_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_path(main_config_path: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    return (main_config_path.parent / candidate).resolve()


def _requested_environment(main: dict[str, Any]) -> str:
    env_value = os.environ.get("JARVIS_ENV", main.get("environment", "auto"))
    env_value = str(env_value).strip().lower()
    if env_value not in VALID_ENVIRONMENTS:
        return "auto"
    return env_value


def _check_llm_health(llm: dict[str, Any]) -> bool:
    health = llm.get("health_check") or {}
    url = health.get("url") or llm.get("base_url")
    if not url:
        return False

    method = str(health.get("method", "GET")).upper()
    timeout = float(health.get("timeout_seconds", 5))
    headers: dict[str, str] = {}

    api_key_env = llm.get("api_key_env")
    if api_key_env:
        token = os.environ.get(api_key_env, "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

    try:
        if method == "HEAD":
            response = requests.head(url, headers=headers, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, timeout=timeout)
        return response.status_code < 500
    except requests.RequestException:
        return False


def _load_profile(main_config_path: Path, main: dict[str, Any], name: str) -> dict[str, Any]:
    profiles = main.get("profiles") or {}
    relative = profiles.get(name)
    if not relative:
        raise FileNotFoundError(
            f"No profile path configured for '{name}' in config.yaml (profiles.{name})."
        )

    profile_path = _resolve_path(main_config_path, str(relative))
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile file not found: {profile_path}")

    return _read_yaml(profile_path)


def resolve_active_config(
    config_path: str | Path = DEFAULT_MAIN_CONFIG,
) -> dict[str, Any]:
    """
    Returns merged configuration with llm.active_profile set to the chosen profile.
    """
    main_path = Path(config_path).resolve()
    main = _read_yaml(main_path)

    fallback = bool(main.get("fallback_to_local", True))
    mode = _requested_environment(main)

    local_profile = _load_profile(main_path, main, "local")
    deployed_profile: dict[str, Any] | None = None
    deployed_path = (main.get("profiles") or {}).get("deployed")
    if deployed_path:
        deployed_file = _resolve_path(main_path, str(deployed_path))
        if deployed_file.is_file():
            deployed_profile = _read_yaml(deployed_file)

    chosen_name = "local"
    chosen_profile = local_profile
    fallback_used = False

    def try_deployed() -> bool:
        nonlocal chosen_name, chosen_profile, fallback_used
        if not deployed_profile or "llm" not in deployed_profile:
            return False
        if not _check_llm_health(deployed_profile["llm"]):
            return False
        chosen_name = "deployed"
        chosen_profile = deployed_profile
        return True

    if mode == "local":
        chosen_name = "local"
        chosen_profile = local_profile
    elif mode == "deployed":
        if try_deployed():
            pass
        elif fallback:
            chosen_name = "local"
            chosen_profile = local_profile
            fallback_used = True
        else:
            chosen_name = "deployed"
            chosen_profile = deployed_profile or local_profile
    else:  # auto
        if try_deployed():
            pass
        else:
            chosen_name = "local"
            chosen_profile = local_profile
            if deployed_profile is not None:
                fallback_used = True

    merged = _deep_merge(main, chosen_profile)
    merged["llm"] = merged.get("llm") or {}
    merged["llm"]["active_profile"] = chosen_name
    merged["llm"]["fallback_used"] = fallback_used
    merged["llm"]["requested_environment"] = mode
    return merged
