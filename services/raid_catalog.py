"""World of Warcraft class/spec metadata for raid signups."""

from __future__ import annotations

import discord

from config.emoji_overrides import CLASS_EMOJIS, SPEC_EMOJIS

ROLE_MELEE = "melee"
ROLE_RANGED = "ranged"
ROLE_HEALER = "healer"
ROLE_TANK = "tank"

ROLE_LABELS = {
    ROLE_MELEE: "Melee",
    ROLE_RANGED: "Ranged",
    ROLE_HEALER: "Healers",
    ROLE_TANK: "Tanks",
}

ROLE_EMOJIS = {
    ROLE_MELEE: "⚔️",
    ROLE_RANGED: "🏹",
    ROLE_HEALER: "➕",
    ROLE_TANK: "🛡️",
}

CLASSES = {
    "dk": {
        "name": "DK",
        "emoji": "💀",
        "specs": {
            "blood": {"name": "Blood", "role": ROLE_TANK},
            "frost": {"name": "Frost", "role": ROLE_MELEE},
            "unholy": {"name": "Unholy", "role": ROLE_MELEE},
        },
    },
    "dh": {
        "name": "DH",
        "emoji": "😈",
        "specs": {
            "havoc": {"name": "Havoc", "role": ROLE_MELEE},
            "vengeance": {"name": "Vengeance", "role": ROLE_TANK},
        },
    },
    "warrior": {
        "name": "Warrior",
        "emoji": "⚔️",
        "specs": {
            "arms": {"name": "Arms", "role": ROLE_MELEE},
            "fury": {"name": "Fury", "role": ROLE_MELEE},
            "protection": {"name": "Protection", "role": ROLE_TANK},
        },
    },
    "monk": {
        "name": "Monk",
        "emoji": "🍃",
        "specs": {
            "brewmaster": {"name": "Brewmaster", "role": ROLE_TANK},
            "mistweaver": {"name": "Mistweaver", "role": ROLE_HEALER},
            "windwalker": {"name": "Windwalker", "role": ROLE_MELEE},
        },
    },
    "druid": {
        "name": "Druid",
        "emoji": "🐻",
        "specs": {
            "balance": {"name": "Balance", "role": ROLE_RANGED},
            "feral": {"name": "Feral", "role": ROLE_MELEE},
            "guardian": {"name": "Guardian", "role": ROLE_TANK},
            "restoration": {"name": "Restoration", "role": ROLE_HEALER},
        },
    },
    "paladin": {
        "name": "Paladin",
        "emoji": "🔆",
        "specs": {
            "holy": {"name": "Holy", "role": ROLE_HEALER},
            "protection": {"name": "Protection", "role": ROLE_TANK},
            "retribution": {"name": "Retribution", "role": ROLE_MELEE},
        },
    },
    "hunter": {
        "name": "Hunter",
        "emoji": "🏹",
        "specs": {
            "beast_mastery": {"name": "Beast Mastery", "role": ROLE_RANGED},
            "marksmanship": {"name": "Marksmanship", "role": ROLE_RANGED},
            "survival": {"name": "Survival", "role": ROLE_MELEE},
        },
    },
    "evoker": {
        "name": "Evoker",
        "emoji": "🐉",
        "specs": {
            "devastation": {"name": "Devastation", "role": ROLE_RANGED},
            "preservation": {"name": "Preservation", "role": ROLE_HEALER},
            "augmentation": {"name": "Augmentation", "role": ROLE_RANGED},
        },
    },
    "rogue": {
        "name": "Rogue",
        "emoji": "🗡️",
        "specs": {
            "assassination": {"name": "Assassination", "role": ROLE_MELEE},
            "outlaw": {"name": "Outlaw", "role": ROLE_MELEE},
            "subtlety": {"name": "Subtlety", "role": ROLE_MELEE},
        },
    },
    "priest": {
        "name": "Priest",
        "emoji": "✨",
        "specs": {
            "discipline": {"name": "Discipline", "role": ROLE_HEALER},
            "holy": {"name": "Holy", "role": ROLE_HEALER},
            "shadow": {"name": "Shadow", "role": ROLE_RANGED},
        },
    },
    "shaman": {
        "name": "Shaman",
        "emoji": "⚡",
        "specs": {
            "elemental": {"name": "Elemental", "role": ROLE_RANGED},
            "enhancement": {"name": "Enhancement", "role": ROLE_MELEE},
            "restoration": {"name": "Restoration", "role": ROLE_HEALER},
        },
    },
    "mage": {
        "name": "Mage",
        "emoji": "🔮",
        "specs": {
            "arcane": {"name": "Arcane", "role": ROLE_RANGED},
            "fire": {"name": "Fire", "role": ROLE_RANGED},
            "frost": {"name": "Frost", "role": ROLE_RANGED},
        },
    },
    "warlock": {
        "name": "Warlock",
        "emoji": "🍋",
        "specs": {
            "affliction": {"name": "Affliction", "role": ROLE_RANGED},
            "demonology": {"name": "Demonology", "role": ROLE_RANGED},
            "destruction": {"name": "Destruction", "role": ROLE_RANGED},
        },
    },
}


def get_class(class_key: str | None) -> dict | None:
    if not class_key:
        return None
    return CLASSES.get(class_key)


def get_spec(class_key: str | None, spec_key: str | None) -> dict | None:
    class_data = get_class(class_key)
    if not class_data or not spec_key:
        return None
    return class_data["specs"].get(spec_key)


def _resolve_emoji(value: str, guild: discord.Guild | None = None) -> str:
    raw = value.strip()
    if not raw:
        return ""
    if raw.startswith("<:") or raw.startswith("<a:"):
        return raw

    name = raw.strip(":")
    if guild is not None:
        emoji = discord.utils.get(guild.emojis, name=name)
        if emoji is not None:
            return str(emoji)
    return ""


def class_emoji(class_key: str | None, guild: discord.Guild | None = None) -> str:
    class_data = get_class(class_key)
    if not class_data:
        return ""
    override = CLASS_EMOJIS.get(class_key or "", "")
    return _resolve_emoji(override, guild) or class_data["emoji"]


def spec_emoji(
    class_key: str | None,
    spec_key: str | None,
    guild: discord.Guild | None = None,
) -> str:
    if not class_key or not spec_key:
        return ""
    override = SPEC_EMOJIS.get(f"{class_key}:{spec_key}", "")
    return _resolve_emoji(override, guild)


def spec_display_name(class_key: str | None, spec_key: str | None) -> str:
    spec_data = get_spec(class_key, spec_key)
    return spec_data["name"] if spec_data else ""


def format_spec_icon_or_name(
    class_key: str | None,
    spec_key: str | None,
    guild: discord.Guild | None = None,
) -> str:
    """Return only the spec marker for a signup row."""
    icon = spec_emoji(class_key, spec_key, guild)
    if icon:
        return icon
    spec_name = spec_display_name(class_key, spec_key)
    return spec_name if spec_name else "No spec"


def format_class_spec(
    class_key: str | None,
    spec_key: str | None,
    guild: discord.Guild | None = None,
) -> str:
    class_data = get_class(class_key)
    if not class_data:
        return "No class"
    class_icon = class_emoji(class_key, guild)
    spec_icon = spec_emoji(class_key, spec_key, guild)
    if spec_icon:
        return f"{class_icon} {spec_icon} {class_data['name']}"
    spec_data = get_spec(class_key, spec_key)
    if not spec_data:
        return f"{class_icon} {class_data['name']}"
    return f"{class_icon} {spec_data['name']} {class_data['name']}"


def signup_role(class_key: str | None, spec_key: str | None) -> str:
    spec_data = get_spec(class_key, spec_key)
    if spec_data:
        return spec_data["role"]
    return ROLE_RANGED
