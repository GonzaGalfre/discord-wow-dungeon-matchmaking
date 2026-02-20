"""
Leaderboard service for the WoW Mythic+ LFG Bot.

This module handles leaderboard formatting and embed building for stats.

Multi-guild support: Leaderboards can be filtered by guild.
"""

from datetime import datetime
from typing import Dict, List, Optional

import discord

from models.stats import (
    get_weekly_stats,
    get_all_time_stats,
    get_player_stats,
    get_previous_week_number,
    get_current_week_number,
)


def build_weekly_leaderboard_embed(
    week_number: Optional[int] = None,
    guild_id: Optional[int] = None
) -> discord.Embed:
    """
    Build an embed showing the weekly leaderboard.
    
    Args:
        week_number: Specific week to show (default: current week)
        guild_id: Filter by guild (None for global stats)
        
    Returns:
        discord.Embed with weekly leaderboard
    """
    stats = get_weekly_stats(week_number, guild_id=guild_id)
    
    # Format week display
    year = stats["week_number"] // 100
    week = stats["week_number"] % 100
    week_display = f"Semana {week}, {year}"
    
    embed = discord.Embed(
        title="🏆 Tabla de Posiciones Semanal",
        description=f"**{week_display}**",
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    
    if stats["total_keys"] == 0:
        embed.add_field(
            name="📭 Sin Datos",
            value="No se han completado llaves esta semana todavía.",
            inline=False,
        )
        return embed
    
    # Summary stats
    embed.add_field(
        name="📊 Resumen",
        value=(
            f"🗝️ **Llaves completadas:** {stats['total_keys']}\n"
            f"📈 **Promedio:** +{stats['avg_key_level']}\n"
            f"⭐ **Más alta:** +{stats['max_key_level']}"
        ),
        inline=False,
    )
    
    # Top players
    if stats["player_stats"]:
        leaderboard_lines = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, player in enumerate(stats["player_stats"][:10]):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            leaderboard_lines.append(
                f"{medal} <@{player['user_id']}> — **{player['key_count']}** llaves"
            )
        
        embed.add_field(
            name="🎮 Top Jugadores",
            value="\n".join(leaderboard_lines),
            inline=False,
        )
    
    embed.set_footer(text="¡Sigue haciendo llaves para subir en la tabla!")
    
    return embed


def build_alltime_leaderboard_embed(guild_id: Optional[int] = None) -> discord.Embed:
    """
    Build an embed showing the all-time leaderboard.
    
    Args:
        guild_id: Filter by guild (None for global stats)
    
    Returns:
        discord.Embed with all-time leaderboard
    """
    stats = get_all_time_stats(guild_id=guild_id)
    
    embed = discord.Embed(
        title="🏆 Tabla de Posiciones - Histórico",
        description="Estadísticas desde el inicio de los tiempos",
        color=discord.Color.purple(),
        timestamp=datetime.now(),
    )
    
    if stats["total_keys"] == 0:
        embed.add_field(
            name="📭 Sin Datos",
            value="No se han completado llaves todavía.",
            inline=False,
        )
        return embed
    
    # Summary stats
    embed.add_field(
        name="📊 Resumen Total",
        value=(
            f"🗝️ **Llaves completadas:** {stats['total_keys']}\n"
            f"📈 **Promedio:** +{stats['avg_key_level']}\n"
            f"⭐ **Más alta:** +{stats['max_key_level']}"
        ),
        inline=False,
    )
    
    # Top players all time
    if stats["top_players"]:
        leaderboard_lines = []
        medals = ["🥇", "🥈", "🥉"]
        
        for i, player in enumerate(stats["top_players"][:10]):
            medal = medals[i] if i < 3 else f"`{i+1}.`"
            leaderboard_lines.append(
                f"{medal} <@{player['user_id']}> — **{player['key_count']}** llaves"
            )
        
        embed.add_field(
            name="🎮 Top Jugadores (Todo el Tiempo)",
            value="\n".join(leaderboard_lines),
            inline=False,
        )
    
    embed.set_footer(text="Estadísticas acumuladas desde el inicio")
    
    return embed


def build_player_stats_embed(
    user_id: int,
    username: str,
    guild_id: Optional[int] = None
) -> discord.Embed:
    """
    Build an embed showing a specific player's stats.
    
    Args:
        user_id: Discord user ID
        username: Display name
        guild_id: Filter by guild (None for global stats)
        
    Returns:
        discord.Embed with player stats
    """
    stats = get_player_stats(user_id, guild_id=guild_id)
    
    embed = discord.Embed(
        title=f"📊 Estadísticas de {username}",
        color=discord.Color.blue(),
        timestamp=datetime.now(),
    )
    
    if stats["total_keys"] == 0:
        embed.add_field(
            name="📭 Sin Datos",
            value="Este jugador no ha completado llaves todavía.",
            inline=False,
        )
        return embed
    
    # General stats
    embed.add_field(
        name="🗝️ Llaves Completadas",
        value=(
            f"**Esta semana:** {stats['weekly_keys']}\n"
            f"**Total:** {stats['total_keys']}"
        ),
        inline=True,
    )
    
    embed.add_field(
        name="⭐ Llave Más Alta",
        value=f"+{stats['max_key_level']}",
        inline=True,
    )
    
    if stats["favorite_role"]:
        role = stats["favorite_role"]
        embed.add_field(
            name="💪 Rol Favorito",
            value=f"{role['emoji']} {role['display_name']}",
            inline=True,
        )
    
    return embed


def build_weekly_announcement_embed(
    guild_id: Optional[int] = None,
    use_current_week: bool = False
) -> discord.Embed:
    """
    Build the weekly announcement embed for the previous (or current) week.
    
    By default, this is sent on Tuesday reset to summarize the previous week.
    When use_current_week=True (e.g. manual /anuncio for testing), shows current week.
    
    Args:
        guild_id: Filter by guild (None for global stats)
        use_current_week: If True, show current week; if False, show previous week
    
    Returns:
        discord.Embed with weekly summary announcement
    """
    if use_current_week:
        target_week = get_current_week_number()
    else:
        target_week = get_previous_week_number()
    
    stats = get_weekly_stats(target_week, guild_id=guild_id)
    
    # Format week display
    year = target_week // 100
    week = target_week % 100
    week_display = f"Semana {week}"
    
    if use_current_week:
        description = f"Resumen de la semana actual (**{week_display}**):"
    else:
        description = f"¡El reset ha llegado! Aquí está el resumen de la **{week_display}**:"
    
    embed = discord.Embed(
        title="📢 Resumen Semanal de Mythic+",
        description=description,
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    
    if stats["total_keys"] == 0:
        if use_current_week:
            empty_msg = "No se han completado llaves esta semana todavía. ¡A farmear!"
        else:
            empty_msg = (
                "No se completaron llaves la semana pasada. ¡A farmear esta semana!\n\n"
                f"*Nota: Este resumen muestra la **{week_display}**. "
                "Las llaves de esta semana aparecen en /leaderboard*"
            )
        embed.add_field(
            name="📭 Semana Tranquila",
            value=empty_msg,
            inline=False,
        )
        return embed
    
    # Main announcement
    week_ref = "esta semana" if use_current_week else "la semana pasada"
    announcement = f"🗝️ Se completaron **{stats['total_keys']} llaves** {week_ref}!"
    
    if stats["top_player"]:
        top = stats["top_player"]
        announcement += (
            f"\n\n🏆 **MVP de la Semana:** <@{top['user_id']}>\n"
            f"Con **{top['key_count']} llaves** completadas!"
        )
    
    embed.add_field(
        name="🎉 ¡Felicidades a todos!",
        value=announcement,
        inline=False,
    )
    
    # Extra stats
    embed.add_field(
        name="📈 Estadísticas",
        value=(
            f"**Promedio de llave:** +{stats['avg_key_level']}\n"
            f"**Llave más alta:** +{stats['max_key_level']}"
        ),
        inline=True,
    )
    
    # Top 3 players
    if len(stats["player_stats"]) > 1:
        medals = ["🥇", "🥈", "🥉"]
        top_3_lines = []
        
        for i, player in enumerate(stats["player_stats"][:3]):
            top_3_lines.append(
                f"{medals[i]} <@{player['user_id']}> — {player['key_count']} llaves"
            )
        
        embed.add_field(
            name="🏅 Podio",
            value="\n".join(top_3_lines),
            inline=True,
        )
    
    embed.set_footer(text="¡Nueva semana, nuevas oportunidades! ¡A por esas llaves!")
    
    return embed
