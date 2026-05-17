"""
v7.0 — JSON/YAML I/O for memory files.
Replaces duplicated load_json/save_json/parse_iso functions across scripts.
"""
import json
import os
from datetime import datetime


def load_json(path, default=None):
    """Load JSON with safe fallback. Default {} if not specified."""
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return default


def save_json(path, data, indent=2):
    """Save JSON creating parent directory if needed. UTF-8 forced."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def parse_iso(s):
    """Parse ISO datetime tolerantly. Returns None if invalid."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
        except (ValueError, TypeError):
            return None


# v7.1-B — YAML helpers (used by manage_agent_automations)
def load_yaml(path, default=None):
    """Load YAML with safe fallback. Default [] if not specified."""
    import yaml
    if default is None:
        default = []
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
        return data if data is not None else default
    except (FileNotFoundError, yaml.YAMLError):
        return default


def save_yaml(path, data):
    """Save YAML creating parent directory if needed."""
    import yaml
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
