"""Confirmed roster Discord publishing."""

from __future__ import annotations

from io import BytesIO
from datetime import datetime
import re

import discord

from models.raid_signup import mark_roster_published
from services.raid_catalog import CLASSES, ROLE_HEALER, ROLE_MELEE, ROLE_RANGED, ROLE_TANK, signup_role


ROLE_DPS = "dps"
ROLE_ORDER = (ROLE_TANK, ROLE_DPS, ROLE_HEALER)
ROLE_TITLES = {
    ROLE_TANK: "Tanks",
    ROLE_HEALER: "Healers",
    ROLE_DPS: "DPS",
}

CLASS_COLORS = {
    "dk": "#C41E3A",
    "dh": "#A330C9",
    "druid": "#FF7C0A",
    "evoker": "#33937F",
    "hunter": "#AAD372",
    "mage": "#3FC7EB",
    "monk": "#00FF98",
    "paladin": "#F48CBA",
    "priest": "#FFFFFF",
    "rogue": "#FFF468",
    "shaman": "#0070DD",
    "warlock": "#8788EE",
    "warrior": "#C69B6D",
}


def _class_name(class_key: str | None) -> str:
    if not class_key:
        return "-"
    return CLASSES.get(class_key, {}).get("name", class_key)


def _spec_name(class_key: str | None, spec_key: str | None) -> str:
    if not class_key or not spec_key:
        return "-"
    class_data = CLASSES.get(class_key, {})
    return class_data.get("specs", {}).get(spec_key, {}).get("name", spec_key)


def _class_color(class_key: str | None) -> str:
    return CLASS_COLORS.get(class_key or "", "#ffffff")


def _group_roster(roster: list[dict]) -> dict[str, list[dict]]:
    grouped = {role: [] for role in ROLE_ORDER}
    for player in roster:
        role = player.get("roster_role") or signup_role(player.get("class_key"), player.get("spec_key"))
        if role in {ROLE_MELEE, ROLE_RANGED}:
            role = ROLE_DPS
        if role not in grouped:
            role = ROLE_DPS
        grouped[role].append(player)
    return grouped


def _format_starts_at(starts_at: str | None) -> str:
    if not starts_at:
        return ""
    match = re.search(r"<t:(\d+):[a-zA-Z]>", starts_at)
    if not match:
        return starts_at
    return datetime.fromtimestamp(int(match.group(1))).strftime("%a %b %d, %H:%M")


def _roster_text(event: dict, roster: list[dict]) -> str:
    bench_roster = event.get("bench_roster") if isinstance(event.get("bench_roster"), list) else []
    lines = [f"**{event['title']} confirmed roster**", _format_starts_at(event.get("starts_at")), ""]
    grouped = _group_roster(roster)
    for role in ROLE_ORDER:
        players = grouped[role]
        if not players:
            continue
        lines.append(f"__{ROLE_TITLES[role]} ({len(players)})__")
        for player in players:
            class_key = player.get("class_key")
            spec_key = player.get("spec_key")
            lines.append(f"- {player.get('display_name', 'Unknown')} - {_spec_name(class_key, spec_key)} {_class_name(class_key)}")
        lines.append("")
    if bench_roster:
        lines.append("")
        lines.append("---------------- BENCH ----------------")
        lines.append(f"__Bench ({len(bench_roster)})__")
        for player in bench_roster:
            class_key = player.get("class_key")
            spec_key = player.get("spec_key")
            lines.append(f"- {player.get('display_name', 'Unknown')} - {_spec_name(class_key, spec_key)} {_class_name(class_key)}")
    return "\n".join(lines).strip()


def _build_roster_png(event: dict, roster: list[dict]) -> BytesIO:
    from PIL import Image, ImageDraw, ImageFont

    width = 900
    padding = 36
    row_height = 34
    section_gap = 18
    grouped = _group_roster(roster)
    bench_roster = event.get("bench_roster") if isinstance(event.get("bench_roster"), list) else []
    row_count = len(roster) + len(bench_roster) + sum(1 for role in ROLE_ORDER if grouped[role]) + (1 if bench_roster else 0)
    height = max(360, padding * 2 + 110 + row_count * row_height + section_gap * 4)

    image = Image.new("RGB", (width, height), "#141414")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("arialbd.ttf", 34)
        header_font = ImageFont.truetype("arialbd.ttf", 22)
        text_font = ImageFont.truetype("arial.ttf", 20)
        small_font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        title_font = header_font = text_font = small_font = ImageFont.load_default()

    draw.rounded_rectangle((14, 14, width - 14, height - 14), radius=22, fill="#1f1f1f", outline="#c9a227", width=2)
    draw.text((padding, padding), f"{event['title']} confirmed roster", fill="#f4d06f", font=title_font)
    draw.text((padding, padding + 44), _format_starts_at(event.get("starts_at")), fill="#b8b8b8", font=small_font)
    draw.text((width - padding - 150, padding + 44), f"{len(roster)} raid + {len(bench_roster)} bench", fill="#b8b8b8", font=small_font)

    y = padding + 92
    for role in ROLE_ORDER:
        players = grouped[role]
        if not players:
            continue
        draw.text((padding, y), f"{ROLE_TITLES[role]} ({len(players)})", fill="#f4d06f", font=header_font)
        y += row_height
        for player in players:
            class_key = player.get("class_key")
            spec_key = player.get("spec_key")
            name = str(player.get("display_name") or "Unknown")
            detail = f"{_spec_name(class_key, spec_key)} {_class_name(class_key)}"
            color = _class_color(class_key)
            draw.text((padding + 18, y), name, fill=color, font=text_font)
            draw.text((width - padding - 300, y), detail, fill=color, font=text_font)
            y += row_height
        y += section_gap

    if bench_roster:
        y += 10
        draw.line((padding, y, width - padding, y), fill="#d97706", width=3)
        y += 20
        draw.text((padding, y), f"BENCH ({len(bench_roster)})", fill="#f59e0b", font=header_font)
        y += row_height
        for player in bench_roster:
            class_key = player.get("class_key")
            spec_key = player.get("spec_key")
            name = str(player.get("display_name") or "Unknown")
            detail = f"{_spec_name(class_key, spec_key)} {_class_name(class_key)}"
            color = _class_color(class_key)
            draw.text((padding + 18, y), name, fill=color, font=text_font)
            draw.text((width - padding - 300, y), detail, fill=color, font=text_font)
            y += row_height

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


async def publish_confirmed_roster(client: discord.Client, event: dict) -> bool:
    """Publish a confirmed roster request. Returns True when handled."""
    requested_at = event.get("roster_publish_requested_at")
    if not requested_at or requested_at == event.get("roster_published_at"):
        return False

    roster = event.get("confirmed_roster")
    bench_roster = event.get("bench_roster")
    if not isinstance(roster, list):
        roster = []
    if not isinstance(bench_roster, list):
        bench_roster = []
    if not roster and not bench_roster:
        return False

    channel_id = event.get("roster_publish_channel_id") or event.get("channel_id")
    if not channel_id:
        return False

    channel = client.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await client.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden):
            return False

    if not isinstance(channel, discord.abc.Messageable):
        return False

    event = {**event, "bench_roster": bench_roster}
    content = _roster_text(event, roster)
    try:
        image = _build_roster_png(event, roster)
        await channel.send(content=f"**{event['title']} confirmed roster**", file=discord.File(image, filename="confirmed-roster.png"))
    except Exception:
        await channel.send(content=content)

    mark_roster_published(event["id"], str(requested_at))
    return True
