"""
Views module for the WoW Mythic+ LFG Bot.

This module contains Discord UI components (Views, Buttons, Selects).
"""

from views.join_queue import JoinQueueView, QueueTypeSelectView
from views.role_selection import (
    RoleSelectView,
    MultiRoleSelectView,
    KeyBracketSelectView,
    KeystoneChoiceView,
    KeystoneLevelSelectView,
)
from views.group_selection import (
    GroupCompositionView,
    GroupKeyBracketSelectView,
    GroupKeystoneChoiceView,
    GroupKeystoneLevelSelectView,
)
from views.party import PartyCompleteView
from views.queue_entry_actions import QueueEntryActionsView

__all__ = [
    # Join queue views
    "JoinQueueView",
    "QueueTypeSelectView",
    # Role selection views (solo)
    "RoleSelectView",
    "MultiRoleSelectView",
    "KeyBracketSelectView",
    "KeystoneChoiceView",
    "KeystoneLevelSelectView",
    # Group selection views
    "GroupCompositionView",
    "GroupKeyBracketSelectView",
    "GroupKeystoneChoiceView",
    "GroupKeystoneLevelSelectView",
    # Party views
    "PartyCompleteView",
    # Queue action views
    "QueueEntryActionsView",
]

