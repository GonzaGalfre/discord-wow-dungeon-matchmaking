"""
Development/Testing Cog for the WoW Mythic+ LFG Bot.

This module contains admin-only commands for testing and debugging
multi-user scenarios without needing multiple Discord accounts.

⚠️ IMPORTANT: These commands are for TESTING ONLY and should be used carefully.
"""

import random
from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config.settings import ROLES, MIN_KEY_LEVEL, MAX_KEY_LEVEL, PARTY_COMPOSITION
from models.queue import queue_manager
from services.matchmaking import (
    get_users_with_overlap,
    is_group_entry,
    get_entry_player_count,
    get_role_counts,
)
from services.match_flow import trigger_matchmaking_for_entry
from services.queue_preferences import validate_queue_key_range
from event_logger import log_event


class DevCog(commands.Cog):
    """
    Development and testing commands for simulating multiple users.
    
    All commands are admin-only and intended for testing purposes.
    Use these to simulate multi-user scenarios without needing multiple accounts.
    """
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Counter for generating fake user IDs
        self._fake_user_id_counter = 900000000000000000  # Start at a high number to avoid collisions
    
    def _generate_fake_user_id(self) -> int:
        """Generate a unique fake user ID."""
        self._fake_user_id_counter += 1
        return self._fake_user_id_counter
    
    @app_commands.command(
        name="dev_add_player",
        description="[DEV] Añadir un jugador falso a la cola"
    )
    @app_commands.describe(
        nombre="Nombre del jugador falso",
        rol="Rol del jugador",
        key_min="Nivel mínimo de llave",
        key_max="Nivel máximo de llave",
        auto_match="Buscar matches automáticamente (como jugadores reales)"
    )
    @app_commands.choices(rol=[
        app_commands.Choice(name="Tanque", value="tank"),
        app_commands.Choice(name="Sanador", value="healer"),
        app_commands.Choice(name="DPS", value="dps"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def dev_add_player(
        self,
        interaction: discord.Interaction,
        nombre: str,
        rol: str,
        key_min: int,
        key_max: int,
        auto_match: bool = True
    ):
        """
        Add a fake solo player to the queue for testing.
        
        Example: /dev_add_player nombre:Alice rol:tank key_min:5 key_max:10
        """
        guild_id = interaction.guild_id
        
        # Validate key range
        try:
            validate_queue_key_range(key_min, key_max)
        except ValueError:
            await interaction.response.send_message(
                f"⚠️ Rango de llaves inválido. Debe ser 0 o {MIN_KEY_LEVEL}-{MAX_KEY_LEVEL}, y min <= max.",
                ephemeral=True,
            )
            return
        
        # Generate fake user ID
        fake_user_id = self._generate_fake_user_id()
        
        # Add to queue
        queue_manager.add(guild_id, fake_user_id, nombre, key_min, key_max, roles=[rol])
        
        role_info = ROLES[rol]
        
        # Auto-match if enabled (simulates real player behavior)
        if auto_match:
            result = await trigger_matchmaking_for_entry(
                self.bot,
                guild_id,
                fake_user_id,
                key_min,
                key_max,
                source="dev_add_player",
                fallback_channel=interaction.channel,
                triggered_by_user_id=interaction.user.id,
                mention_fake_users=True,
                message_prefix="🔧 **[DEV MATCH AUTO]** ",
            )

            if result.get("matched"):
                await interaction.response.send_message(
                    f"✅ **Jugador añadido y match creado automáticamente:**\n\n"
                    f"👤 **Nombre:** {nombre} (ID: `{fake_user_id}`)\n"
                    f"{role_info['emoji']} **Rol:** {role_info['name']}\n"
                    f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                    f"🎉 **Match formado con {result.get('user_count', 0)} jugadores!**\n"
                    f"📍 Ver match en el canal de emparejamientos.",
                    ephemeral=True,
                )
            else:
                # No match, just waiting
                await interaction.response.send_message(
                    f"✅ **Jugador añadido (esperando match):**\n\n"
                    f"👤 **Nombre:** {nombre} (ID: `{fake_user_id}`)\n"
                    f"{role_info['emoji']} **Rol:** {role_info['name']}\n"
                    f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                    f"⏳ Sin jugadores compatibles aún. Esperando...",
                    ephemeral=True,
                )
        else:
            # Manual mode - no auto-matching
            await interaction.response.send_message(
                f"✅ **Jugador añadido a la cola (modo manual):**\n\n"
                f"👤 **Nombre:** {nombre} (ID: `{fake_user_id}`)\n"
                f"{role_info['emoji']} **Rol:** {role_info['name']}\n"
                f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                f"💡 *Usa `/dev_force_match` para crear matches manualmente.*",
                ephemeral=True,
            )
    
    @app_commands.command(
        name="dev_add_group",
        description="[DEV] Añadir un grupo falso a la cola"
    )
    @app_commands.describe(
        nombre="Nombre del líder del grupo",
        tanks="Número de tanques (0-1)",
        healers="Número de sanadores (0-1)",
        dps="Número de DPS (0-3)",
        key_min="Nivel mínimo de llave",
        key_max="Nivel máximo de llave",
        auto_match="Buscar matches automáticamente (como jugadores reales)"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_add_group(
        self,
        interaction: discord.Interaction,
        nombre: str,
        tanks: int,
        healers: int,
        dps: int,
        key_min: int,
        key_max: int,
        auto_match: bool = True
    ):
        """
        Add a fake group to the queue for testing.
        
        Example: /dev_add_group nombre:BobGroup tanks:1 healers:0 dps:2 key_min:8 key_max:12
        """
        guild_id = interaction.guild_id
        
        # Validate composition
        if tanks < 0 or tanks > 1 or healers < 0 or healers > 1 or dps < 0 or dps > 3:
            await interaction.response.send_message(
                "⚠️ Composición inválida. Límites: Tanques (0-1), Sanadores (0-1), DPS (0-3).",
                ephemeral=True,
            )
            return
        
        total = tanks + healers + dps
        if total == 0 or total > 5:
            await interaction.response.send_message(
                "⚠️ El grupo debe tener entre 1 y 5 jugadores.",
                ephemeral=True,
            )
            return
        
        # Validate key range
        try:
            validate_queue_key_range(key_min, key_max)
        except ValueError:
            await interaction.response.send_message(
                f"⚠️ Rango de llaves inválido. Debe ser 0 o {MIN_KEY_LEVEL}-{MAX_KEY_LEVEL}, y min <= max.",
                ephemeral=True,
            )
            return
        
        # Generate fake user ID
        fake_user_id = self._generate_fake_user_id()
        
        composition = {
            "tank": tanks,
            "healer": healers,
            "dps": dps,
        }
        
        # Add to queue
        queue_manager.add(guild_id, fake_user_id, nombre, key_min, key_max, composition=composition)
        
        # Auto-match if enabled (simulates real player behavior)
        if auto_match:
            result = await trigger_matchmaking_for_entry(
                self.bot,
                guild_id,
                fake_user_id,
                key_min,
                key_max,
                source="dev_add_group",
                fallback_channel=interaction.channel,
                triggered_by_user_id=interaction.user.id,
                mention_fake_users=True,
                message_prefix="🔧 **[DEV MATCH AUTO]** ",
            )

            if result.get("matched"):
                await interaction.response.send_message(
                    f"✅ **Grupo añadido y match creado automáticamente:**\n\n"
                    f"👥 **Líder:** {nombre} (ID: `{fake_user_id}`)\n"
                    f"🛡️ **Composición:** {tanks}T / {healers}H / {dps}D ({total} jugadores)\n"
                    f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                    f"🎉 **Match formado con {result.get('user_count', 0)} jugadores/grupos!**\n"
                    f"📍 Ver match en el canal de emparejamientos.",
                    ephemeral=True,
                )
            else:
                # No match, just waiting
                await interaction.response.send_message(
                    f"✅ **Grupo añadido (esperando match):**\n\n"
                    f"👥 **Líder:** {nombre} (ID: `{fake_user_id}`)\n"
                    f"🛡️ **Composición:** {tanks}T / {healers}H / {dps}D ({total} jugadores)\n"
                    f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                    f"⏳ Sin jugadores compatibles aún. Esperando...",
                    ephemeral=True,
                )
        else:
            # Manual mode - no auto-matching
            await interaction.response.send_message(
                f"✅ **Grupo añadido a la cola (modo manual):**\n\n"
                f"👥 **Líder:** {nombre} (ID: `{fake_user_id}`)\n"
                f"🛡️ **Composición:** {tanks}T / {healers}H / {dps}D ({total} jugadores)\n"
                f"🗝️ **Rango:** {key_min}-{key_max}\n\n"
                f"💡 *Usa `/dev_force_match` para crear matches manualmente.*",
                ephemeral=True,
            )
    
    @app_commands.command(
        name="dev_queue_state",
        description="[DEV] Ver el estado interno de la cola"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_queue_state(self, interaction: discord.Interaction):
        """
        View detailed internal state of the queue.
        
        Shows:
        - All entries with their IDs
        - Whether they have active matches
        - Their roles/compositions
        - Key ranges
        """
        guild_id = interaction.guild_id
        
        if queue_manager.is_empty(guild_id):
            await interaction.response.send_message(
                "📭 **Cola Vacía**\n\nNo hay entradas en la cola.",
                ephemeral=True,
            )
            return
        
        embed = discord.Embed(
            title="🔍 Estado Interno de la Cola (DEV)",
            description="Vista detallada de todas las entradas en la cola.",
            color=discord.Color.orange(),
            timestamp=datetime.now(),
        )
        
        entries = []
        total_players = 0
        active_matches = 0
        
        for user_id, data in queue_manager.items(guild_id):
            # Determine if it's a group or solo
            composition = data.get("composition")
            if composition:
                player_count = sum(composition.values())
                total_players += player_count
                role_str = f"🛡️{composition['tank']} 💚{composition['healer']} ⚔️{composition['dps']}"
                entry_type = f"Grupo ({player_count}p)"
            else:
                total_players += 1
                roles = data.get("roles") or ([data.get("role")] if data.get("role") else [])
                if roles:
                    role_str = " > ".join(
                        f"{ROLES.get(role, {'emoji': '❓', 'name': role})['emoji']} {ROLES.get(role, {'name': role})['name']}"
                        for role in roles
                    )
                else:
                    role_str = "❓ ?"
                entry_type = "Solo"
            
            # Check if has active match
            has_match = data.get("match_message_id") is not None
            if has_match:
                active_matches += 1
                match_status = f"✓ Match: `{data['match_message_id']}`"
            else:
                match_status = "✗ No match"
            
            # Format entry
            entry_str = (
                f"**{data['username']}**\n"
                f"├ ID: `{user_id}`\n"
                f"├ Tipo: {entry_type}\n"
                f"├ Rol/Comp: {role_str}\n"
                f"├ Llaves: {data['key_min']}-{data['key_max']}\n"
                f"└ Estado: {match_status}"
            )
            entries.append(entry_str)
        
        # Split into multiple fields if needed (Discord limit is 1024 chars per field)
        for i, entry in enumerate(entries):
            embed.add_field(
                name=f"Entrada #{i+1}",
                value=entry,
                inline=False,
            )
        
        embed.set_footer(
            text=f"Total: {len(entries)} entradas • {total_players} jugadores • {active_matches} con match activo"
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="dev_force_match",
        description="[DEV] Forzar búsqueda de emparejamientos"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_force_match(self, interaction: discord.Interaction):
        """
        Force matchmaking for all players without active matches.
        
        This simulates what happens when a new player joins - it searches
        for compatible players and creates matches.
        """
        guild_id = interaction.guild_id
        
        # Find all entries without active matches
        available_entries = []
        for user_id, data in queue_manager.items(guild_id):
            if data.get("match_message_id") is None:
                available_entries.append((user_id, data))
        
        if len(available_entries) < 2:
            await interaction.response.send_message(
                "⚠️ Se necesitan al menos 2 jugadores sin match activo para formar un grupo.",
                ephemeral=True,
            )
            return
        
        # Defer response as this might take a moment
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return
        
        matches_created = 0
        
        # Try to match each available entry
        for user_id, data in available_entries:
            # Skip if already matched in this batch
            if queue_manager.get(guild_id, user_id).get("match_message_id") is not None:
                continue
            
            # Try to find matches
            matches = get_users_with_overlap(
                guild_id,
                data["key_min"],
                data["key_max"],
                user_id
            )
            
            if len(matches) < 2:
                continue  # Not enough for a match
            
            result = await trigger_matchmaking_for_entry(
                self.bot,
                guild_id,
                user_id,
                data["key_min"],
                data["key_max"],
                source="dev_force_match",
                fallback_channel=interaction.channel,
                triggered_by_user_id=interaction.user.id,
                mention_fake_users=True,
                message_prefix="🔧 **[DEV MATCH]** ",
            )
            if result.get("matched"):
                matches_created += 1
        
        await interaction.followup.send(
            f"✅ **Emparejamiento forzado completado.**\n\n"
            f"🎮 Matches creados: {matches_created}\n\n"
            f"💡 *Los matches se han enviado al canal de emparejamientos.*",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="dev_remove_player",
        description="[DEV] Eliminar un jugador de la cola por ID"
    )
    @app_commands.describe(
        user_id="ID del usuario a eliminar"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_remove_player(self, interaction: discord.Interaction, user_id: str):
        """
        Remove a specific player from the queue by their user ID.
        
        Useful for cleaning up fake users or testing leave scenarios.
        """
        guild_id = interaction.guild_id
        
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(
                "⚠️ ID inválido. Debe ser un número.",
                ephemeral=True,
            )
            return
        
        entry = queue_manager.get(guild_id, uid)
        if not entry:
            await interaction.response.send_message(
                f"⚠️ No se encontró ningún jugador con ID `{uid}` en la cola.",
                ephemeral=True,
            )
            return
        
        username = entry["username"]
        has_match = entry.get("match_message_id") is not None
        
        queue_manager.remove(guild_id, uid)
        
        await interaction.response.send_message(
            f"✅ **Jugador eliminado de la cola:**\n\n"
            f"👤 {username} (ID: `{uid}`)\n"
            f"📊 Estado: {'Tenía match activo' if has_match else 'Sin match'}\n\n"
            f"💡 *El match message (si existía) seguirá visible pero los botones manejarán la ausencia.*",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="dev_clear_queue",
        description="[DEV] Limpiar toda la cola del servidor"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_clear_queue(self, interaction: discord.Interaction):
        """
        Clear the entire queue for this guild.
        
        ⚠️ WARNING: This removes all entries, including real players!
        """
        guild_id = interaction.guild_id
        
        count = queue_manager.count(guild_id)
        
        if count == 0:
            await interaction.response.send_message(
                "📭 La cola ya está vacía.",
                ephemeral=True,
            )
            return
        
        queue_manager.clear(guild_id)
        
        await interaction.response.send_message(
            f"✅ **Cola limpiada.**\n\n"
            f"🗑️ Se eliminaron {count} entrada(s).\n\n"
            f"⚠️ *Los match messages existentes seguirán visibles pero sus botones no funcionarán correctamente. "
            f"Considera eliminarlos manualmente si es necesario.*",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="dev_simulate_scenario",
        description="[DEV] Simular un escenario de prueba completo"
    )
    @app_commands.describe(
        escenario="Escenario a simular"
    )
    @app_commands.choices(escenario=[
        app_commands.Choice(name="Escenario 1: Match Simple (2 jugadores)", value="simple"),
        app_commands.Choice(name="Escenario 2: Múltiples Grupos Independientes", value="multiple"),
        app_commands.Choice(name="Escenario 3: Composición Compleja (5 jugadores)", value="complex"),
        app_commands.Choice(name="Escenario 4: Sin Overlapping (sin matches)", value="no_overlap"),
    ])
    @app_commands.default_permissions(administrator=True)
    async def dev_simulate_scenario(self, interaction: discord.Interaction, escenario: str):
        """
        Simulate a complete test scenario with multiple fake players.
        
        This creates a full setup to test specific situations.
        """
        guild_id = interaction.guild_id
        
        # Clear existing queue first
        queue_manager.clear(guild_id)

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return
        
        if escenario == "simple":
            # Scenario 1: Simple match (2 players)
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Alice", 5, 10, role="tank")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Bob", 5, 10, role="healer")
            
            description = (
                "**Escenario 1: Match Simple**\n\n"
                "✓ Alice (Tank, 5-10)\n"
                "✓ Bob (Healer, 5-10)\n\n"
                "Deberían formar un match juntos."
            )
        
        elif escenario == "multiple":
            # Scenario 2: Multiple independent groups
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Alice", 5, 10, role="tank")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Bob", 5, 10, role="healer")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Charlie", 8, 15, role="dps")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Diana", 8, 15, role="dps")
            
            description = (
                "**Escenario 2: Múltiples Grupos Independientes**\n\n"
                "✓ Alice (Tank, 5-10) + Bob (Healer, 5-10) → Match 1\n"
                "✓ Charlie (DPS, 8-15) + Diana (DPS, 8-15) → Match 2\n\n"
                "Usa `/dev_force_match` para crear ambos matches."
            )
        
        elif escenario == "complex":
            # Scenario 3: Complex composition (5 players)
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Tank1", 10, 15, role="tank")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "Healer1", 10, 15, role="healer")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "DPS1", 10, 15, role="dps")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "DPS2", 10, 15, role="dps")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "DPS3", 10, 15, role="dps")
            
            description = (
                "**Escenario 3: Composición Completa (5 jugadores)**\n\n"
                "✓ Tank1 (Tank, 10-15)\n"
                "✓ Healer1 (Healer, 10-15)\n"
                "✓ DPS1, DPS2, DPS3 (DPS, 10-15)\n\n"
                "Deberían formar un grupo completo de 5."
            )
        
        elif escenario == "no_overlap":
            # Scenario 4: No overlapping ranges
            queue_manager.add(guild_id, self._generate_fake_user_id(), "LowKey", 2, 5, role="tank")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "MidKey", 8, 12, role="healer")
            queue_manager.add(guild_id, self._generate_fake_user_id(), "HighKey", 15, 20, role="dps")
            
            description = (
                "**Escenario 4: Sin Overlapping**\n\n"
                "✓ LowKey (Tank, 2-5)\n"
                "✓ MidKey (Healer, 8-12)\n"
                "✓ HighKey (DPS, 15-20)\n\n"
                "NO deberían formar matches (sin overlap de rangos)."
            )
        
        else:
            await interaction.followup.send("⚠️ Escenario desconocido.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="✅ Escenario Simulado",
            description=description,
            color=discord.Color.green(),
        )
        
        embed.add_field(
            name="📋 Próximos Pasos",
            value=(
                "1. Usa `/dev_queue_state` para ver el estado\n"
                "2. Usa `/dev_force_match` para crear matches\n"
                "3. Usa `/cola` para ver cómo lo ven los usuarios\n"
                "4. Usa `/dev_clear_queue` para limpiar cuando termines"
            ),
            inline=False,
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(
        name="dev_test",
        description="[TEST] Comando de prueba - debería aparecer para todos"
    )
    async def dev_test(self, interaction: discord.Interaction):
        """Test command without admin requirement to verify commands are syncing."""
        await interaction.response.send_message(
            "✅ ¡El comando de prueba funciona! Los dev commands están cargados correctamente.",
            ephemeral=True,
        )
    
    @app_commands.command(
        name="dev_sync",
        description="[DEV] Forzar sincronización inmediata de comandos a este servidor"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_sync(self, interaction: discord.Interaction):
        """
        Force sync commands to the current guild for immediate availability.
        
        This copies all global commands to this specific server so they appear
        immediately instead of waiting up to 1 hour for global sync.
        
        NOTE: This can cause duplicate commands if global sync has already completed.
        Use /dev_clear_sync to remove duplicates and rely on global commands.
        """
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return
        try:
            # Copy global commands to this guild
            interaction.client.tree.copy_global_to(guild=interaction.guild)
            synced = await interaction.client.tree.sync(guild=interaction.guild)
            
            await interaction.followup.send(
                f"✅ **Comandos sincronizados inmediatamente**\n\n"
                f"📊 {len(synced)} comandos copiados a **{interaction.guild.name}**\n\n"
                f"⚠️ **Nota:** Si ves comandos duplicados, usa `/dev_clear_sync` para limpiar "
                f"las copias locales y usar solo comandos globales.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error sincronizando: {e}",
                ephemeral=True,
            )
    
    @app_commands.command(
        name="dev_clear_sync",
        description="[DEV] Limpiar comandos locales y usar solo comandos globales"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_clear_sync(self, interaction: discord.Interaction):
        """
        Clear guild-specific commands and rely on global commands only.
        
        Use this to remove duplicate commands that appear after using /dev_sync
        when the global sync has already completed.
        """
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return
        try:
            # Clear all guild-specific commands
            interaction.client.tree.clear_commands(guild=interaction.guild)
            await interaction.client.tree.sync(guild=interaction.guild)
            
            await interaction.followup.send(
                f"✅ **Comandos locales eliminados**\n\n"
                f"Ahora el servidor **{interaction.guild.name}** usa solo comandos globales.\n\n"
                f"💡 Los comandos deberían dejar de estar duplicados en unos segundos. "
                f"Si no, reinicia Discord.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error limpiando comandos: {e}",
                ephemeral=True,
            )
    
    @app_commands.command(
        name="dev_info",
        description="[DEV] Información sobre los comandos de desarrollo"
    )
    @app_commands.default_permissions(administrator=True)
    async def dev_info(self, interaction: discord.Interaction):
        """
        Display information about all dev commands and how to use them.
        """
        embed = discord.Embed(
            title="🔧 Comandos de Desarrollo",
            description="Herramientas para probar escenarios multi-usuario sin necesitar múltiples cuentas.",
            color=discord.Color.blue(),
        )
        
        embed.add_field(
            name="📥 Añadir Jugadores",
            value=(
                "`/dev_add_player` - Añadir jugador solo\n"
                "`/dev_add_group` - Añadir grupo\n"
                "`/dev_simulate_scenario` - Escenarios predefinidos"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="🔍 Inspección",
            value=(
                "`/dev_queue_state` - Ver estado interno completo\n"
                "`/cola` - Ver como usuario normal"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="⚙️ Acciones",
            value=(
                "`/dev_force_match` - Forzar búsqueda de matches\n"
                "`/dev_remove_player` - Eliminar por ID\n"
                "`/dev_clear_queue` - Limpiar toda la cola"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="💡 Flujo de Prueba Recomendado",
            value=(
                "1. **Simular escenario:** `/dev_simulate_scenario`\n"
                "2. **Ver estado:** `/dev_queue_state`\n"
                "3. **Crear matches:** `/dev_force_match`\n"
                "4. **Inspeccionar resultados:** Revisar matches en el canal\n"
                "5. **Limpiar:** `/dev_clear_queue`"
            ),
            inline=False,
        )
        
        embed.add_field(
            name="⚠️ Notas Importantes",
            value=(
                "• Los jugadores falsos tienen IDs > 900000000000000000\n"
                "• Los matches se marcan como `[DEV MATCH]`\n"
                "• Puedes mezclar jugadores reales y falsos\n"
                "• Los match messages no se eliminan automáticamente"
            ),
            inline=False,
        )
        
        embed.set_footer(text="Solo disponible para administradores • Usa con cuidado en producción")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """
    Setup function for loading the dev cog.
    
    Called by bot.load_extension().
    """
    await bot.add_cog(DevCog(bot))
