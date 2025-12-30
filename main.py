"""
=============================================================================
WoW Mythic+ LFG Bot - Un "Soft Matchmaker" para Guilds de Discord
=============================================================================

Este bot permite a los miembros del guild indicar que están disponibles para
niveles específicos de Piedras Angulares. Cuando varias personas buscan
rangos que se solapan, todos son notificados para formar grupo.

Autor: Tu Guild
Versión: 1.1.0
Discord.py Versión: 2.0+
=============================================================================
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

# Cargar variables de entorno desde el archivo .env
# Esto mantiene los datos sensibles (como el token) fuera del código
load_dotenv()

# Obtener el token del bot desde las variables de entorno
# ¡NUNCA pongas tu token directamente en el código!
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# El ID del canal donde estará el botón "Unirse a Cola" (limpio, minimalista)
# Los usuarios deben configurar esto en su archivo .env
LFG_CHANNEL_ID = int(os.getenv("LFG_CHANNEL_ID", "0"))

# El ID del canal donde se publicarán las notificaciones de emparejamiento
# Puede ser el mismo canal o uno diferente para mantener el canal principal limpio
MATCH_CHANNEL_ID = int(os.getenv("MATCH_CHANNEL_ID", "0"))

# =============================================================================
# CONSTANTES - Definiciones de roles con emojis
# =============================================================================

# Diccionario que mapea nombres de rol a su información de visualización
# Esto facilita añadir/modificar roles en un solo lugar
ROLES = {
    "tank": {"name": "Tanque", "emoji": "🛡️"},
    "healer": {"name": "Sanador", "emoji": "💚"},
    "dps": {"name": "DPS", "emoji": "⚔️"},
}

# Rango de niveles de llave disponibles (Mythic+ va de 2 a 20+)
# Usamos 2-20 como rango razonable para la mayoría de jugadores
MIN_KEY_LEVEL = 2
MAX_KEY_LEVEL = 20

# Composición de grupo para Mythic+ (límites máximos por rol)
# Un grupo de M+ tiene: 1 Tank, 1 Healer, 3 DPS = 5 jugadores
PARTY_COMPOSITION = {
    "tank": 1,
    "healer": 1,
    "dps": 3,
}

# =============================================================================
# ALMACENAMIENTO EN MEMORIA DE LA COLA
# =============================================================================

# La cola almacena todos los usuarios que actualmente buscan grupo
# Estructura: {user_id: {"username": str, "role": str, "role_emoji": str, 
#                        "key_min": int, "key_max": int, "timestamp": datetime}}
#
# ¿Por qué un diccionario con user_id como clave?
# - Búsqueda rápida O(1) para verificar si un usuario ya está en cola
# - Fácil de sobrescribir si el usuario se vuelve a apuntar
# - Simple para eliminar un usuario específico cuando se va
queue: Dict[int, dict] = {}


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def is_valid_composition(users: List[dict]) -> bool:
    """
    Verifica si un grupo de usuarios forma una composición válida de M+.
    
    Una composición válida no excede los límites:
    - Máximo 1 Tanque
    - Máximo 1 Sanador
    - Máximo 3 DPS
    
    Args:
        users: Lista de usuarios con su información de rol
        
    Returns:
        True si la composición es válida, False si no
        
    Ejemplos:
        >>> is_valid_composition([{"role": "tank"}, {"role": "healer"}])
        True
        >>> is_valid_composition([{"role": "tank"}, {"role": "tank"}])
        False  # 2 tanks no es válido
    """
    # Contar cuántos de cada rol hay
    role_counts = {"tank": 0, "healer": 0, "dps": 0}
    
    for user in users:
        role = user.get("role")
        if role in role_counts:
            role_counts[role] += 1
    
    # Verificar que ningún rol exceda su límite
    for role, count in role_counts.items():
        if count > PARTY_COMPOSITION[role]:
            return False
    
    return True


def get_role_counts(users: List[dict]) -> Dict[str, int]:
    """
    Cuenta cuántos usuarios hay de cada rol.
    
    Args:
        users: Lista de usuarios
        
    Returns:
        Diccionario con el conteo de cada rol
    """
    counts = {"tank": 0, "healer": 0, "dps": 0}
    for user in users:
        role = user.get("role")
        if role in counts:
            counts[role] += 1
    return counts


def ranges_overlap(range1: Tuple[int, int], range2: Tuple[int, int]) -> bool:
    """
    Verifica si dos rangos de llaves se solapan.
    
    Dos rangos [a, b] y [c, d] se solapan si max(a,c) <= min(b,d)
    
    Args:
        range1: Tupla (min, max) del primer rango
        range2: Tupla (min, max) del segundo rango
        
    Returns:
        True si hay solapamiento, False si no
        
    Ejemplos:
        >>> ranges_overlap((9, 11), (10, 14))  # Solapan en 10-11
        True
        >>> ranges_overlap((2, 5), (10, 15))   # No se solapan
        False
        >>> ranges_overlap((5, 10), (8, 12))   # Solapan en 8-10
        True
    """
    min1, max1 = range1
    min2, max2 = range2
    return max(min1, min2) <= min(max1, max2)


def get_overlapping_range(range1: Tuple[int, int], range2: Tuple[int, int]) -> Optional[Tuple[int, int]]:
    """
    Calcula el rango de solapamiento entre dos rangos.
    
    Args:
        range1: Tupla (min, max) del primer rango
        range2: Tupla (min, max) del segundo rango
        
    Returns:
        Tupla (min, max) del solapamiento, o None si no hay solapamiento
    """
    if not ranges_overlap(range1, range2):
        return None
    
    min1, max1 = range1
    min2, max2 = range2
    return (max(min1, min2), min(max1, max2))


def get_users_with_overlap(key_min: int, key_max: int, new_user_id: int) -> List[dict]:
    """
    Encuentra usuarios en la cola con rango solapado Y composición de grupo válida.
    
    Esta función construye un grupo válido de forma incremental:
    1. Empieza con el nuevo usuario
    2. Añade otros usuarios si tienen rango solapado Y no rompen la composición
    
    Args:
        key_min: Nivel mínimo de llave buscado
        key_max: Nivel máximo de llave buscado
        new_user_id: ID del usuario que acaba de unirse (para incluirlo primero)
        
    Returns:
        Lista de usuarios que forman un grupo válido con rangos solapados
    """
    target_range = (key_min, key_max)
    
    # Empezar con el nuevo usuario
    if new_user_id not in queue:
        return []
    
    new_user_data = queue[new_user_id]
    matched_group = [{"user_id": new_user_id, **new_user_data}]
    
    # Buscar otros usuarios compatibles
    for user_id, data in queue.items():
        if user_id == new_user_id:
            continue  # Ya está en el grupo
        
        user_range = (data["key_min"], data["key_max"])
        
        # Verificar solapamiento de rango
        if not ranges_overlap(target_range, user_range):
            continue
        
        # Crear grupo temporal para verificar composición
        potential_user = {"user_id": user_id, **data}
        temp_group = matched_group + [potential_user]
        
        # Solo añadir si la composición sigue siendo válida
        if is_valid_composition(temp_group):
            matched_group.append(potential_user)
    
    return matched_group


def calculate_common_range(users: List[dict]) -> Tuple[int, int]:
    """
    Calcula el rango común donde TODOS los usuarios se solapan.
    
    Args:
        users: Lista de usuarios con sus rangos
        
    Returns:
        Tupla (min, max) del rango común
    """
    if not users:
        return (MIN_KEY_LEVEL, MAX_KEY_LEVEL)
    
    # El rango común es el máximo de los mínimos y el mínimo de los máximos
    common_min = max(u["key_min"] for u in users)
    common_max = min(u["key_max"] for u in users)
    
    return (common_min, common_max)


def add_to_queue(user_id: int, username: str, role: str, key_min: int, key_max: int) -> None:
    """
    Añade o actualiza un usuario en la cola.
    
    Si el usuario ya está en la cola, su entrada se sobrescribe.
    Esto aplica la regla: un usuario = una entrada en cola.
    
    Args:
        user_id: ID de usuario de Discord
        username: Nombre para mostrar en notificaciones
        role: El rol que quiere jugar (tank/healer/dps)
        key_min: Nivel mínimo de llave
        key_max: Nivel máximo de llave
    """
    queue[user_id] = {
        "username": username,
        "role": role,
        "role_emoji": ROLES[role]["emoji"],
        "key_min": key_min,
        "key_max": key_max,
        "timestamp": datetime.now(),
    }


def remove_from_queue(user_id: int) -> bool:
    """
    Elimina un usuario de la cola.
    
    Args:
        user_id: ID de usuario de Discord a eliminar
        
    Returns:
        True si el usuario fue eliminado, False si no estaba en la cola
    """
    return queue.pop(user_id, None) is not None


def build_match_embed(users: List[dict]) -> discord.Embed:
    """
    Crea un embed profesional para notificaciones de emparejamiento.
    
    Este embed se envía públicamente cuando 2+ personas tienen rangos que se solapan.
    
    Args:
        users: Lista de entradas de usuarios que coinciden
        
    Returns:
        discord.Embed listo para enviar
    """
    # Calcular el rango común donde todos coinciden
    common_range = calculate_common_range(users)
    
    # Contar roles actuales
    role_counts = get_role_counts(users)
    
    # Crear el embed con un color dorado/naranja (temática WoW)
    embed = discord.Embed(
        title="🔔 ¡Grupo Encontrado!",
        description="Los siguientes jugadores buscan grupo:",
        color=discord.Color.gold(),
        timestamp=datetime.now(),
    )
    
    # Construir la lista de jugadores con roles y emojis
    player_lines = []
    for user in users:
        # Formato: "🛡️ @Usuario (Tanque) - Llaves 9-15"
        player_lines.append(
            f"{user['role_emoji']} <@{user['user_id']}> ({ROLES[user['role']]['name']}) "
            f"— Llaves {user['key_min']}-{user['key_max']}"
        )
    
    # Añadir la lista de jugadores como un campo
    embed.add_field(
        name=f"🗝️ Rango Compatible: {common_range[0]}-{common_range[1]}",
        value="\n".join(player_lines),
        inline=False,
    )
    
    # Mostrar composición actual y lo que falta
    composition_parts = []
    needed_parts = []
    
    # Tanque
    if role_counts["tank"] > 0:
        composition_parts.append(f"🛡️ {role_counts['tank']}/1")
    else:
        needed_parts.append("🛡️ Tanque")
    
    # Sanador
    if role_counts["healer"] > 0:
        composition_parts.append(f"💚 {role_counts['healer']}/1")
    else:
        needed_parts.append("💚 Sanador")
    
    # DPS
    if role_counts["dps"] > 0:
        composition_parts.append(f"⚔️ {role_counts['dps']}/3")
    if role_counts["dps"] < 3:
        needed_parts.append(f"⚔️ DPS ({3 - role_counts['dps']} más)")
    
    # Añadir campo de composición
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
    
    # Añadir pie de página útil
    embed.set_footer(text="¡Haz clic en 'Grupo Completo' cuando todos estén listos!")
    
    return embed


# =============================================================================
# VISTAS DE INTERFAZ DE DISCORD
# =============================================================================

def build_confirmation_embed(matched_user_ids: List[int], confirmed_ids: set) -> discord.Embed:
    """
    Crea un embed para mostrar el estado de confirmación del grupo.
    
    Args:
        matched_user_ids: Lista de IDs de usuarios en el match
        confirmed_ids: Set de IDs de usuarios que ya confirmaron
        
    Returns:
        discord.Embed con el estado de confirmación
    """
    embed = discord.Embed(
        title="⏳ Confirmación de Grupo",
        description="Todos los jugadores deben confirmar para formar el grupo.",
        color=discord.Color.orange(),
        timestamp=datetime.now(),
    )
    
    # Mostrar estado de cada jugador
    status_lines = []
    for uid in matched_user_ids:
        if uid in confirmed_ids:
            status_lines.append(f"✅ <@{uid}> — Confirmado")
        elif uid in queue:
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


class ConfirmationView(discord.ui.View):
    """
    Vista para confirmar la formación del grupo.
    
    Cada jugador debe hacer clic en 'Confirmar' o 'Rechazar'.
    - Si todos confirman: grupo formado, todos eliminados de cola
    - Si alguien rechaza: solo ese jugador es eliminado, los demás vuelven a buscar
    """
    
    def __init__(self, matched_user_ids: List[int], original_embed: discord.Embed):
        super().__init__(timeout=None)
        self.matched_user_ids = matched_user_ids
        self.original_embed = original_embed  # Guardamos el embed original por si hay que volver
        self.confirmed_ids: set = set()  # IDs de usuarios que han confirmado
    
    @discord.ui.button(
        label="Confirmar",
        style=discord.ButtonStyle.success,
        emoji="✅",
    )
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Maneja el clic del botón Confirmar."""
        user_id = interaction.user.id
        
        # Verificar que quien hace clic era parte del match
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores del grupo pueden confirmar.",
                ephemeral=True,
            )
            return
        
        # Verificar que el usuario sigue en cola
        if user_id not in queue:
            await interaction.response.send_message(
                "⚠️ Ya no estás en la cola.",
                ephemeral=True,
            )
            return
        
        # Verificar si ya confirmó
        if user_id in self.confirmed_ids:
            await interaction.response.send_message(
                "ℹ️ Ya has confirmado. Esperando a los demás...",
                ephemeral=True,
            )
            return
        
        # Añadir a confirmados
        self.confirmed_ids.add(user_id)
        
        # Verificar cuántos siguen en cola y cuántos han confirmado
        users_still_in_queue = [uid for uid in self.matched_user_ids if uid in queue]
        all_confirmed = all(uid in self.confirmed_ids for uid in users_still_in_queue)
        
        if all_confirmed and len(users_still_in_queue) >= 2:
            # ¡Todos confirmaron! Grupo formado
            removed_users = []
            for uid in users_still_in_queue:
                removed_users.append(f"<@{uid}>")
                remove_from_queue(uid)
            
            await interaction.response.send_message(
                f"🎉 **¡Grupo formado!**\n\n"
                f"El grupo se ha formado por {', '.join(removed_users)} "
                f"y serán eliminados de la cola.\n\n"
                f"¡Buena suerte en la mazmorra! 🗝️",
                ephemeral=False,
            )
            
            # Eliminar el mensaje de confirmación
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        else:
            # Actualizar el embed para mostrar el nuevo estado
            embed = build_confirmation_embed(self.matched_user_ids, self.confirmed_ids)
            await interaction.response.edit_message(embed=embed, view=self)
    
    @discord.ui.button(
        label="Rechazar",
        style=discord.ButtonStyle.danger,
        emoji="❌",
    )
    async def reject_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Maneja el clic del botón Rechazar."""
        user_id = interaction.user.id
        
        # Verificar que quien hace clic era parte del match
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores del grupo pueden rechazar.",
                ephemeral=True,
            )
            return
        
        # Eliminar al usuario de la cola
        was_in_queue = remove_from_queue(user_id)
        
        if was_in_queue:
            await interaction.response.send_message(
                "✅ Has rechazado y salido de la cola. ¡Hasta la próxima!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ Ya no estabas en la cola.",
                ephemeral=True,
            )
        
        # Verificar si quedan suficientes jugadores
        users_still_in_queue = [uid for uid in self.matched_user_ids if uid in queue]
        
        # Notificar por DM a los que habían confirmado (sin revelar quién rechazó)
        for uid in self.confirmed_ids:
            if uid != user_id:  # No enviar al que rechazó
                try:
                    user = await interaction.client.fetch_user(uid)
                    await user.send(
                        "😔 **Alguien ha rechazado la confirmación de grupo.**\n\n"
                        "Sigues en la cola esperando más jugadores. "
                        "¡No te preocupes, pronto encontrarás otro grupo!"
                    )
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    # El usuario tiene DMs desactivados o hubo un error
                    pass
        
        if len(users_still_in_queue) < 2:
            # No quedan suficientes jugadores, eliminar el mensaje
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
        else:
            # Eliminar el mensaje de confirmación actual
            try:
                await interaction.message.delete()
            except (discord.errors.NotFound, discord.errors.Forbidden):
                pass
            
            self.confirmed_ids.discard(user_id)
            
            # Reconstruir el embed original con los usuarios que quedan
            users_data = [{"user_id": uid, **queue[uid]} for uid in users_still_in_queue]
            new_embed = build_match_embed(users_data)
            
            # Crear nueva vista
            new_view = PartyCompleteView(users_still_in_queue)
            
            # Mencionar a todos los que quedan (nuevo mensaje = notificación)
            mentions = " ".join(f"<@{uid}>" for uid in users_still_in_queue)
            
            channel = interaction.channel
            if channel:
                await channel.send(
                    content=mentions,  # Solo ping, sin decir quién rechazó
                    embed=new_embed,
                    view=new_view,
                )


class PartyCompleteView(discord.ui.View):
    """
    Vista que contiene los botones 'Grupo Completo' y 'Salir de Cola'.
    
    Se adjunta a los mensajes de notificación de emparejamiento.
    - 'Grupo Completo': Inicia el proceso de confirmación
    - 'Salir de Cola': Elimina solo al usuario que hace clic
    
    Nota: Esta vista no es completamente persistente después de un reinicio
    del bot porque necesita saber qué usuarios estaban en el match.
    Como la cola también está en memoria, esto es aceptable.
    """
    
    def __init__(self, matched_user_ids: List[int]):
        super().__init__(timeout=None)
        self.matched_user_ids = matched_user_ids
    
    @discord.ui.button(
        label="Grupo Completo",
        style=discord.ButtonStyle.success,
        emoji="✅",
    )
    async def party_complete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Maneja el clic del botón Grupo Completo.
        
        Inicia el proceso de confirmación donde todos deben aceptar.
        """
        user_id = interaction.user.id
        
        # Verificar que quien hace clic era parte del match
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores del grupo pueden usar estos botones.",
                ephemeral=True,
            )
            return
        
        # Verificar que el usuario sigue en cola
        if user_id not in queue:
            await interaction.response.send_message(
                "⚠️ Ya no estás en la cola.",
                ephemeral=True,
            )
            return
        
        # Verificar cuántos siguen en cola
        users_still_in_queue = [uid for uid in self.matched_user_ids if uid in queue]
        
        if len(users_still_in_queue) < 2:
            await interaction.response.send_message(
                "⚠️ No hay suficientes jugadores en cola para formar grupo.",
                ephemeral=True,
            )
            return
        
        # Guardar el embed actual
        original_embed = interaction.message.embeds[0] if interaction.message.embeds else None
        
        # Crear la vista de confirmación
        confirmation_view = ConfirmationView(users_still_in_queue, original_embed)
        
        # El usuario que inició ya está confirmando automáticamente
        confirmation_view.confirmed_ids.add(user_id)
        
        # Crear el embed de confirmación
        embed = build_confirmation_embed(users_still_in_queue, confirmation_view.confirmed_ids)
        
        # Mencionar a TODOS para que reciban notificación (nuevo mensaje = notificación)
        mentions = " ".join(f"<@{uid}>" for uid in users_still_in_queue)
        
        # Usar defer para evitar el timeout de la interacción
        await interaction.response.defer()
        
        # Eliminar el mensaje de match anterior
        try:
            await interaction.message.delete()
        except (discord.errors.NotFound, discord.errors.Forbidden):
            pass
        
        # Enviar NUEVO mensaje de confirmación (esto SÍ notifica a todos)
        channel = interaction.channel
        if channel:
            await channel.send(
                content=f"🔔 {mentions} — ¡Confirmen para formar el grupo!",
                embed=embed,
                view=confirmation_view,
            )
    
    @discord.ui.button(
        label="Salir de Cola",
        style=discord.ButtonStyle.danger,
        emoji="🚪",
    )
    async def leave_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Maneja el clic del botón Salir de Cola.
        
        Elimina SOLO al usuario que hace clic de la cola.
        Útil cuando alguien ya no puede jugar pero los demás sí.
        Si no queda nadie del match en cola, elimina el mensaje.
        """
        user_id = interaction.user.id
        
        # Verificar que quien hace clic era parte del match
        if user_id not in self.matched_user_ids:
            await interaction.response.send_message(
                "⚠️ Solo los jugadores del grupo pueden usar estos botones.",
                ephemeral=True,
            )
            return
        
        was_in_queue = remove_from_queue(user_id)
        
        if was_in_queue:
            await interaction.response.send_message(
                "✅ Has salido de la cola. ¡Hasta la próxima!",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "ℹ️ Ya no estabas en la cola.",
                ephemeral=True,
            )
        
        # Verificar si queda alguien del match original en la cola
        anyone_still_queued = any(uid in queue for uid in self.matched_user_ids)
        
        # Si no queda nadie, eliminar el mensaje de notificación
        if not anyone_still_queued:
            try:
                await interaction.message.delete()
            except discord.errors.NotFound:
                pass
            except discord.errors.Forbidden:
                pass


class KeyRangeMaxSelectView(discord.ui.View):
    """
    Vista para seleccionar el nivel MÁXIMO de llave.
    
    Esta aparece DESPUÉS de que el usuario selecciona su nivel mínimo.
    Solo muestra opciones >= al mínimo seleccionado.
    """
    
    def __init__(self, role: str, key_min: int):
        super().__init__(timeout=60)
        self.role = role
        self.key_min = key_min
        
        # Crear el select dinámicamente para mostrar solo opciones válidas
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Llaves hasta +{i}",
                emoji="🔼" if i == MAX_KEY_LEVEL else "🗝️",
            )
            for i in range(key_min, MAX_KEY_LEVEL + 1)
        ]
        
        # Crear y añadir el select
        self.key_select = discord.ui.Select(
            placeholder=f"Selecciona nivel máximo ({key_min}-{MAX_KEY_LEVEL})...",
            options=options,
            custom_id="key_max_select",
        )
        self.key_select.callback = self.key_max_selected
        self.add_item(self.key_select)
    
    async def key_max_selected(self, interaction: discord.Interaction):
        """
        Maneja la selección del nivel máximo de llave.
        
        Aquí es donde ocurre la magia:
        1. Añadir usuario a la cola
        2. Buscar coincidencias
        3. Confirmar espera O enviar notificación de emparejamiento
        """
        key_max = int(self.key_select.values[0])
        user_id = interaction.user.id
        username = interaction.user.display_name
        
        # Añadir el usuario a la cola (o actualizar si ya está)
        add_to_queue(user_id, username, self.role, self.key_min, key_max)
        
        # Buscar quién más tiene rangos que se solapan Y roles compatibles
        matches = get_users_with_overlap(self.key_min, key_max, user_id)
        
        if len(matches) == 1:
            # Solo este usuario tiene rango compatible - esperando a otros
            role_info = ROLES[self.role]
            await interaction.response.edit_message(
                content=f"✅ **¡Estás en la cola!**\n\n"
                f"{role_info['emoji']} **Rol:** {role_info['name']}\n"
                f"🗝️ **Rango de Llaves:** {self.key_min}-{key_max}\n\n"
                f"¡Serás notificado cuando otros busquen llaves compatibles!\n\n"
                f"*Este mensaje se cerrará en 5 segundos...*",
                view=None,  # Quitar los botones/selects
            )
            
            # Esperar y luego eliminar el mensaje efímero
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass  # El mensaje ya fue eliminado
        else:
            # ¡Múltiples personas encontradas! Enviar notificación pública
            await interaction.response.edit_message(
                content=f"🎉 **¡Buenas noticias!** {len(matches)} jugadores buscan llaves compatibles.\n"
                f"Se ha enviado una notificación al canal de emparejamientos.\n\n"
                f"*Este mensaje se cerrará en 5 segundos...*",
                view=None,
            )
            
            # Obtener el canal de emparejamientos
            match_channel = interaction.client.get_channel(MATCH_CHANNEL_ID)
            
            # Si no se configuró MATCH_CHANNEL_ID, usar el canal actual como fallback
            if not match_channel:
                match_channel = interaction.channel
            
            if match_channel:
                embed = build_match_embed(matches)
                mentions = " ".join(f"<@{u['user_id']}>" for u in matches)
                
                # Extraer los IDs de usuario para pasarlos a la vista
                matched_user_ids = [u["user_id"] for u in matches]
                
                await match_channel.send(
                    content=mentions,
                    embed=embed,
                    view=PartyCompleteView(matched_user_ids),
                )
            
            # Esperar y luego eliminar el mensaje efímero
            await asyncio.sleep(5)
            try:
                await interaction.delete_original_response()
            except discord.errors.NotFound:
                pass


class KeyRangeMinSelectView(discord.ui.View):
    """
    Vista para seleccionar el nivel MÍNIMO de llave.
    
    Esta aparece DESPUÉS de que el usuario selecciona su rol.
    """
    
    def __init__(self, role: str):
        super().__init__(timeout=60)
        self.role = role
        
        # Crear opciones para todos los niveles disponibles
        options = [
            discord.SelectOption(
                label=f"Nivel {i}",
                value=str(i),
                description=f"Llaves desde +{i}",
                emoji="🔽" if i == MIN_KEY_LEVEL else "🗝️",
            )
            for i in range(MIN_KEY_LEVEL, MAX_KEY_LEVEL + 1)
        ]
        
        self.key_select = discord.ui.Select(
            placeholder=f"Selecciona nivel mínimo ({MIN_KEY_LEVEL}-{MAX_KEY_LEVEL})...",
            options=options,
            custom_id="key_min_select",
        )
        self.key_select.callback = self.key_min_selected
        self.add_item(self.key_select)
    
    async def key_min_selected(self, interaction: discord.Interaction):
        """
        Maneja la selección del nivel mínimo.
        
        Muestra el selector de nivel máximo después de elegir el mínimo.
        """
        key_min = int(self.key_select.values[0])
        role_info = ROLES[self.role]
        
        await interaction.response.edit_message(
            content=f"{role_info['emoji']} **{role_info['name']}** seleccionado.\n"
                    f"🔽 **Mínimo:** Nivel {key_min}\n\n"
                    f"Ahora, selecciona tu **nivel máximo** de llave:",
            view=KeyRangeMaxSelectView(self.role, key_min),
        )


class RoleSelectView(discord.ui.View):
    """
    Vista para seleccionar el rol del usuario (Tanque/Sanador/DPS).
    
    Este es el primer paso después de hacer clic en "Unirse a Cola".
    Usa botones para una selección rápida y clara.
    """
    
    def __init__(self):
        super().__init__(timeout=60)
    
    async def handle_role_selection(
        self, interaction: discord.Interaction, role: str
    ):
        """
        Manejador común para todos los botones de rol.
        
        Muestra la selección de rango de llaves después de elegir un rol.
        """
        role_info = ROLES[role]
        
        await interaction.response.edit_message(
            content=f"{role_info['emoji']} **{role_info['name']}** seleccionado.\n\n"
                    f"Ahora, selecciona tu **nivel mínimo** de llave:",
            view=KeyRangeMinSelectView(role),
        )
    
    @discord.ui.button(
        label="Tanque",
        style=discord.ButtonStyle.primary,
        emoji="🛡️",
    )
    async def tank_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Maneja la selección de Tanque."""
        await self.handle_role_selection(interaction, "tank")
    
    @discord.ui.button(
        label="Sanador",
        style=discord.ButtonStyle.success,
        emoji="💚",
    )
    async def healer_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Maneja la selección de Sanador."""
        await self.handle_role_selection(interaction, "healer")
    
    @discord.ui.button(
        label="DPS",
        style=discord.ButtonStyle.danger,
        emoji="⚔️",
    )
    async def dps_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Maneja la selección de DPS."""
        await self.handle_role_selection(interaction, "dps")


class JoinQueueView(discord.ui.View):
    """
    La vista principal persistente con el botón "Unirse a Cola".
    
    Este es el punto de entrada para todo el sistema LFG.
    Se mantiene en el canal LFG y sobrevive a reinicios del bot.
    """
    
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(
        label="Unirse a Cola",
        style=discord.ButtonStyle.success,
        emoji="🎮",
        custom_id="lfg:join_queue",
    )
    async def join_queue_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """
        Maneja el clic del botón Unirse a Cola.
        
        Inicia el flujo de selección de rol.
        La respuesta es efímera (solo el usuario que hace clic la ve).
        """
        await interaction.response.send_message(
            "**🎮 ¿Buscando grupo para Mythic+?**\n\n"
            "Primero, selecciona tu rol:",
            view=RoleSelectView(),
            ephemeral=True,
        )


# =============================================================================
# CLASE DEL BOT
# =============================================================================

class LFGBot(commands.Bot):
    """
    Clase personalizada del Bot para el sistema LFG.
    
    Heredamos de commands.Bot para sobrescribir setup_hook(),
    que es el mejor lugar para registrar vistas persistentes.
    """
    
    def __init__(self):
        intents = discord.Intents.default()
        
        super().__init__(
            command_prefix="!",
            intents=intents,
        )
    
    async def setup_hook(self):
        """
        Se llama antes de que el bot se conecte a Discord.
        
        Aquí registramos las vistas persistentes para que funcionen
        incluso después de reiniciar el bot.
        
        Nota: PartyCompleteView no se registra aquí porque necesita
        los IDs de usuarios del match, que se pierden al reiniciar.
        Esto es aceptable ya que la cola también está en memoria.
        """
        self.add_view(JoinQueueView())
        
        await self.tree.sync()
        print("✅ ¡Comandos slash sincronizados!")
    
    async def on_ready(self):
        """
        Se llama cuando el bot se ha conectado a Discord.
        """
        print(f"🤖 Conectado como {self.user} (ID: {self.user.id})")
        print(f"📡 Conectado a {len(self.guilds)} servidor(es)")
        print("─" * 40)
        
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="grupos de M+ 🗝️",
            )
        )


# =============================================================================
# INSTANCIA DEL BOT Y COMANDOS SLASH
# =============================================================================

bot = LFGBot()


@bot.tree.command(name="setup", description="Publica el botón de LFG en este canal")
@app_commands.default_permissions(administrator=True)
async def setup_command(interaction: discord.Interaction):
    """
    Comando slash para configurar el sistema LFG en un canal.
    
    Publica el botón persistente "Unirse a Cola".
    Solo necesita ejecutarse una vez por canal.
    
    Uso: /setup
    """
    embed = discord.Embed(
        title="🗝️ Buscador de Grupos Mythic+",
        description=(
            "¿Buscas gente para hacer mazmorras Mythic+?\n\n"
            "**Cómo funciona:**\n"
            "1️⃣ Haz clic en el botón de abajo\n"
            "2️⃣ Selecciona tu rol (Tanque, Sanador o DPS)\n"
            "3️⃣ Elige tu rango de llaves preferido\n"
            "4️⃣ ¡Serás notificado cuando otros busquen lo mismo!\n\n"
            "*Solo puedes estar en una cola a la vez.*"
        ),
        color=discord.Color.blue(),
    )
    embed.set_footer(text="¡Feliz cacería de mazmorras! 🎮")
    
    await interaction.channel.send(embed=embed, view=JoinQueueView())
    
    await interaction.response.send_message(
        "✅ ¡El sistema LFG ha sido configurado en este canal!",
        ephemeral=True,
    )


@bot.tree.command(name="cola", description="Ver quién está actualmente en la cola LFG")
async def queue_command(interaction: discord.Interaction):
    """
    Comando slash para ver la cola actual.
    
    Útil para ver quién busca grupo sin unirse.
    
    Uso: /cola
    """
    if not queue:
        await interaction.response.send_message(
            "📭 La cola está vacía. ¡Sé el primero en unirte!",
            ephemeral=True,
        )
        return
    
    embed = discord.Embed(
        title="📋 Cola LFG Actual",
        color=discord.Color.blue(),
        timestamp=datetime.now(),
    )
    
    # Listar todos los usuarios con sus rangos
    user_lines = []
    for user_id, data in queue.items():
        user_lines.append(
            f"{data['role_emoji']} <@{user_id}> — Llaves {data['key_min']}-{data['key_max']}"
        )
    
    embed.add_field(
        name="🎮 Jugadores Buscando",
        value="\n".join(user_lines) if user_lines else "Nadie en cola",
        inline=False,
    )
    
    embed.set_footer(text=f"Total en cola: {len(queue)}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="salir", description="Salir de la cola LFG")
async def leave_command(interaction: discord.Interaction):
    """
    Comando slash para salir de la cola.
    
    Alternativa a hacer clic en el botón Salir de Cola.
    
    Uso: /salir
    """
    if remove_from_queue(interaction.user.id):
        await interaction.response.send_message(
            "✅ ¡Has sido eliminado de la cola!",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "ℹ️ No estabas en la cola.",
            ephemeral=True,
        )


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERROR: ¡DISCORD_TOKEN no encontrado!")
        print("Asegúrate de tener un archivo .env con DISCORD_TOKEN=tu_token_aquí")
        exit(1)
    
    print("🚀 Iniciando Bot LFG de WoW Mythic+...")
    bot.run(DISCORD_TOKEN)
