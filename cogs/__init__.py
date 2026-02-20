"""
Cogs module for the WoW Mythic+ LFG Bot.

This module contains Discord slash commands organized as Cogs.
"""

from cogs.lfg import LFGCog
from cogs.stats import StatsCog
from cogs.dev import DevCog

__all__ = [
    "LFGCog",
    "StatsCog",
    "DevCog",
]

