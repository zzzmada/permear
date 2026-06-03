"""
v7.0 — JSON file I/O for memory.
v7.3-B.2 — save_json with atomic write (temp+rename + LOCK_EX);
            locked_update() context manager for atomic read-modify-write.
"""
import json
import os
import fcntl
from contextlib import contextmanager
from datetime import datetime


def load_json(path, default=None):
    """Load JSON with a safe fallback. Default {} if not specified."""
    if default is None:
        default = {}
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError):
        return default


def save_json(path, data, indent=2):
    """
    v7.3-B.2 — Save JSON with atomic write via temp+rename.
    Acquires LOCK_EX on a .lock file to prevent concurrent writes.
    Creates the parent directory if needed. UTF-8 encoding enforced.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    lock_path = path + ".lock"
    tmp_path = path + ".tmp"

    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


@contextmanager
def locked_update(path, default=None):
    """
    v7.3-B.2 — Context manager for atomic read-modify-write.

    Acquires LOCK_EX before reading, holds it during mutation,
    saves atomically, releases on exit.

    Usage:
        with locked_update('/config/memory/foo.json', default={}) as data:
            data['key'] = 'value'
            # auto-saved on exit (if no exception)

    If an exception occurs inside the block, the file is NOT saved (lock
    released). Mutations must be made in-place on the yielded object — do not
    reassign the local variable to a new object.
    """
    if default is None:
        default = {}

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    lock_path = path + ".lock"
    tmp_path = path + ".tmp"

    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            # Read inside the lock
            try:
                with open(path) as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                # Deep copy via JSON so we don't share the default object
                data = json.loads(json.dumps(default))

            # Yield control for mutations
            yield data

            # Save inside the lock (atomic via temp+rename)
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)


def parse_iso(s):
    """Tolerant ISO datetime parse. Returns None if invalid."""
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
    """Load YAML with a safe fallback. Default [] if not specified."""
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
    """Save YAML, creating the parent directory if needed."""
    import yaml
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
