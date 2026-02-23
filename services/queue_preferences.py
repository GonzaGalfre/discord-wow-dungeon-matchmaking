"""
Queue preference helpers (roles, key brackets, keystone rules).
"""

from typing import Iterable, List, Optional, Tuple

from config.settings import KEY_BRACKETS, MAX_KEY_LEVEL, MIN_KEY_LEVEL


VALID_ROLES = ("tank", "healer", "dps")


def normalize_roles(roles: Optional[Iterable[str]] = None, role: Optional[str] = None) -> List[str]:
    """
    Normalize role preferences to an ordered, deduplicated role list.
    """
    ordered: List[str] = []

    def _push(value: Optional[str]) -> None:
        if not value:
            return
        lowered = str(value).lower().strip()
        if lowered in VALID_ROLES and lowered not in ordered:
            ordered.append(lowered)

    if roles:
        for candidate in roles:
            _push(candidate)

    _push(role)
    return ordered


def bracket_to_range(bracket: str) -> Tuple[int, int]:
    """
    Convert a configured bracket key into its numeric key range.
    """
    info = KEY_BRACKETS.get(bracket)
    if not info:
        raise ValueError(f"Unknown key bracket: {bracket}")
    return int(info["min"]), int(info["max"])


def key_range_to_bracket(key_min: int, key_max: int) -> Optional[str]:
    """
    Resolve a bracket key for a numeric range when it exactly matches a preset.
    """
    for bracket_key, info in KEY_BRACKETS.items():
        if key_min == int(info["min"]) and key_max == int(info["max"]):
            return bracket_key
    return None


def is_valid_queue_key_level(level: int) -> bool:
    """
    Queue supports M0 (0) and Mythic+ keys in the configured range.
    """
    return level == 0 or MIN_KEY_LEVEL <= level <= MAX_KEY_LEVEL


def validate_queue_key_range(key_min: int, key_max: int) -> None:
    """
    Validate queue key ranges, including M0 and mixed 0..20 preference.
    """
    if key_min > key_max:
        raise ValueError("key_min must be <= key_max")
    if not is_valid_queue_key_level(key_min):
        raise ValueError("key_min must be 0 or within configured key level bounds")
    if not is_valid_queue_key_level(key_max):
        raise ValueError("key_max must be 0 or within configured key level bounds")
    if key_min == 1 or key_max == 1:
        raise ValueError("key level 1 is not supported")


def requires_keystone_for_range(key_min: int, key_max: int) -> bool:
    """
    Keystone is required if the effective range includes 2+.
    """
    return key_max >= MIN_KEY_LEVEL


def validate_keystone_input(has_keystone: bool, keystone_level: Optional[int]) -> None:
    """
    Validate keystone fields from queue input.
    """
    if not has_keystone and keystone_level is not None:
        raise ValueError("keystone_level must be empty when has_keystone is false")
    if has_keystone:
        if keystone_level is None:
            raise ValueError("keystone_level is required when has_keystone is true")
        if not (MIN_KEY_LEVEL <= keystone_level <= MAX_KEY_LEVEL):
            raise ValueError(
                f"keystone_level must be between {MIN_KEY_LEVEL} and {MAX_KEY_LEVEL}"
            )
