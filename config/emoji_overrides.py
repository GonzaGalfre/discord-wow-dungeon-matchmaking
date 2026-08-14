"""Optional custom Discord emoji overrides for raid signups.

Values can be either custom emoji names, like "frostdk", or full Discord
emoji mentions, like "<:frostdk:123456789012345678>".

Emoji names are resolved from the server where the signup message is posted.
"""

CLASS_EMOJIS: dict[str, str] = {
    # "dk": "<:class_deathknight:123456789012345678>",
    # "dh": "<:class_demonhunter:123456789012345678>",
}

SPEC_EMOJIS: dict[str, str] = {
    "dk:blood": "blood",
    "dk:frost": "frostdk",
    "dk:unholy": "unholy",
    "dh:havoc": "havoc",
    "dh:vengeance": "vengeance",
    "dh:devourer": "devourer",
    "warrior:arms": "arms",
    "warrior:fury": "fury",
    "warrior:protection": "protwar",
    "monk:brewmaster": "brewmaster",
    "monk:mistweaver": "mistweaver",
    "monk:windwalker": "windwalker",
    "druid:balance": "balance",
    "druid:feral": "feral",
    "druid:guardian": "devourer",
    "druid:restoration": "restodruid",
    "paladin:holy": "holypaladin",
    "paladin:protection": "protpal",
    "paladin:retribution": "retpal",
    "hunter:beast_mastery": "beastmaster",
    "hunter:marksmanship": "marksmanship",
    "hunter:survival": "survival",
    "evoker:devastation": "devastation",
    "evoker:preservation": "prevoker",
    "evoker:augmentation": "augmentation",
    "rogue:assassination": "assrogue",
    "rogue:outlaw": "outlawrogue",
    "rogue:subtlety": "subrogue",
    "priest:discipline": "discipline",
    "priest:holy": "holypriest",
    "priest:shadow": "shadowpriest",
    "shaman:elemental": "elemental",
    "shaman:enhancement": "enhancement",
    "shaman:restoration": "shamrest",
    "mage:arcane": "arcane",
    "mage:fire": "fire",
    "mage:frost": "frost",
    "warlock:affliction": "affliction",
    "warlock:demonology": "demonology",
    "warlock:destruction": "destruction",
}

STATUS_EMOJIS: dict[str, str] = {
    # "attending": "<:check:123456789012345678>",
    # "bench": "<:bench:123456789012345678>",
    # "late": "<:late:123456789012345678>",
    # "tentative": "<:tentative:123456789012345678>",
    # "absence": "<:absence:123456789012345678>",
}
