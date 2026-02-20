"""
Embed builders for the WoW Mythic+ LFG Bot.

This module contains functions to build Discord embeds for
match notifications and confirmation messages.
"""

from datetime import datetime
from typing import List

import discord

from config.settings import ROLES
from models.queue import queue_manager
from services.matchmaking import (
    calculate_common_range,
    get_role_counts,
    is_group_entry,
)


def format_entry_composition(entry: dict) -> str:
    """
    Format the composition of an entry (solo or group) for display.
    
    Args:
        entry: Queue entry
        
    Returns:
        Formatted string with the composition
    """
    composition = entry.get("composition")
    if composition:
        # It's a group: show full composition
        parts = []
        if composition.get("tank", 0) > 0:
            parts.append(f"🛡️{composition['tank']}")
        if composition.get("healer", 0) > 0:
            parts.append(f"💚{composition['healer']}")
        if composition.get("dps", 0) > 0:
            parts.append(f"⚔️{composition['dps']}")
        return " ".join(parts)
    else:
        # It's solo: show individual role
        role = entry.get("role")
        if role and role in ROLES:
            return f"{ROLES[role]['emoji']} {ROLES[role]['name']}"
        return "—"


def build_match_embed(users: List[dict]) -> discord.Embed:
    """
    Create a professional embed for match notifications.
    
    This embed is sent publicly when 2+ entries have overlapping ranges.
    Supports both solo entries and groups.
    
    Args:
        users: List of entries (solo or groups) that match
        
    Returns:
        discord.Embed ready to send
    """
    # Calculate the common range where everyone matches
    common_range = calculate_common_range(users)
    
    # Count current roles (including groups)
    role_counts = get_role_counts(users)
    
    # Create embed with gold/orange color (WoW theme)
    embed = discord.Embed(
        title="🔔 ¡Grupo Encontrado!",
        description="Los siguientes jugadores/grupos buscan grupo:",
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    
    # Build player/group list
    player_lines = []
    for user in users:
        composition = user.get("composition")
        if composition:
            # It's a group: show as leader + composition
            total = sum(composition.values())
            comp_text = format_entry_composition(user)
            player_lines.append(
                f"👥 <@{user['user_id']}> (Grupo: {comp_text}, {total} jugadores) "
                f"— Llaves {user['key_min']}-{user['key_max']}"
            )
        else:
            # It's solo: original format
            role = user.get("role")
            role_info = ROLES.get(role, {"name": "?", "emoji": "❓"})
            player_lines.append(
                f"{role_info['emoji']} <@{user['user_id']}> ({role_info['name']}) "
                f"— Llaves {user['key_min']}-{user['key_max']}"
            )
    
    # Add player list as a field
    embed.add_field(
        name=f"🗝️ Rango Compatible: {common_range[0]}-{common_range[1]}",
        value="\n".join(player_lines),
        inline=False,
    )
    
    # Show current composition and what's missing
    composition_parts = []
    needed_parts = []
    
    # Tank
    if role_counts["tank"] > 0:
        composition_parts.append(f"🛡️ {role_counts['tank']}/1")
    else:
        needed_parts.append("🛡️ Tanque")
    
    # Healer
    if role_counts["healer"] > 0:
        composition_parts.append(f"💚 {role_counts['healer']}/1")
    else:
        needed_parts.append("💚 Sanador")
    
    # DPS
    if role_counts["dps"] > 0:
        composition_parts.append(f"⚔️ {role_counts['dps']}/3")
    if role_counts["dps"] < 3:
        needed_parts.append(f"⚔️ DPS ({3 - role_counts['dps']} más)")
    
    # Add composition field
    composition_text = " • ".join(composition_parts) if composition_parts else "—"
    needed_text = ", ".join(needed_parts) if needed_parts else "¡Grupo completo!"
    
    embed.add_field(
        name="📊 Composición Actual",
        value=composition_text,
        inline=True,
    )
    
    embed.add_field(
        name="🔍 Se Busca",
        value=needed_text,
        inline=True,
    )
    
    # Add helpful footer
    embed.set_footer(text="¡Haz clic en 'Grupo Completo' cuando todos estén listos!")
    
    return embed


def build_confirmation_embed(
    guild_id: int,
    matched_user_ids: List[int], 
    confirmed_ids: set
) -> discord.Embed:
    """
    Create an embed to show group confirmation status.
    
    For groups, only the leader needs to confirm.
    For solo, the individual player confirms.
    
    Args:
        guild_id: Discord guild ID
        matched_user_ids: List of user/leader IDs in the match
        confirmed_ids: Set of user/leader IDs that already confirmed
        
    Returns:
        discord.Embed with confirmation status
    """
    embed = discord.Embed(
        title="⏳ Confirmación de Grupo",
        description="Todos los jugadores/líderes deben confirmar para formar el grupo.",
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )
    
    # Show status of each entry
    status_lines = []
    for uid in matched_user_ids:
        entry = queue_manager.get(guild_id, uid)
        if entry and is_group_entry(entry):
            # It's a group
            comp_text = format_entry_composition(entry)
            if uid in confirmed_ids:
                status_lines.append(f"✅ <@{uid}> (Grupo: {comp_text}) — Confirmado")
            elif queue_manager.contains(guild_id, uid):
                status_lines.append(f"⏳ <@{uid}> (Grupo: {comp_text}) — Esperando confirmación...")
            else:
                status_lines.append(f"❌ <@{uid}> (Grupo) — Ya no está en cola")
        else:
            # It's solo
            if uid in confirmed_ids:
                status_lines.append(f"✅ <@{uid}> — Confirmado")
            elif queue_manager.contains(guild_id, uid):
                status_lines.append(f"⏳ <@{uid}> — Esperando confirmación...")
            else:
                status_lines.append(f"❌ <@{uid}> — Ya no está en cola")
    
    embed.add_field(
        name="Estado de Confirmación",
        value="\n".join(status_lines),
        inline=False,
    )
    
    confirmed_count = len(confirmed_ids)
    total_count = len(matched_user_ids)
    embed.set_footer(text=f"Confirmados: {confirmed_count}/{total_count}")
    
    return embed
