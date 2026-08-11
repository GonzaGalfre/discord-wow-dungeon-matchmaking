"""Voice attendance transition logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol

from models import participation as participation_repo


class RoleLike(Protocol):
    @property
    def id(self) -> int: ...


class MemberLike(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def bot(self) -> bool: ...

    @property
    def roles(self) -> Iterable[RoleLike]: ...


@dataclass(frozen=True, slots=True)
class VoiceTransition:
    guild_id: int
    member: MemberLike
    before_channel_id: int | None
    after_channel_id: int | None
    occurred_at: datetime


def has_any_role(member: MemberLike | None, role_ids: frozenset[int]) -> bool:
    if member is None or member.bot:
        return False
    member_role_ids = {role.id for role in member.roles}
    return bool(member_role_ids & role_ids)


def is_eligible(member: MemberLike | None, settings) -> bool:
    return has_any_role(member, settings.eligible_role_ids | settings.officer_role_ids)


def is_officer(member: MemberLike | None, settings) -> bool:
    return has_any_role(member, settings.officer_role_ids)


class AttendanceService:
    def __init__(self, settings) -> None:
        self.settings = settings

    def _tracked(self, channel_id: int | None) -> bool:
        return channel_id in self.settings.tracked_voice_channel_ids if channel_id is not None else False

    def handle_transition(self, transition: VoiceTransition) -> None:
        before_tracked = self._tracked(transition.before_channel_id)
        after_tracked = self._tracked(transition.after_channel_id)
        if before_tracked == after_tracked and not (before_tracked and after_tracked):
            return
        if not is_eligible(transition.member, self.settings):
            if before_tracked and not after_tracked:
                participation_repo.close_open_voice_session(
                    transition.guild_id, transition.member.id, transition.occurred_at
                )
            return
        if not before_tracked and after_tracked and transition.after_channel_id is not None:
            participation_repo.open_voice_session(
                transition.guild_id, transition.member.id, transition.after_channel_id, transition.occurred_at
            )
            return
        if before_tracked and not after_tracked:
            participation_repo.close_open_voice_session(transition.guild_id, transition.member.id, transition.occurred_at)
            return
        if before_tracked and after_tracked and transition.after_channel_id is not None:
            participation_repo.update_open_voice_channel(
                transition.guild_id, transition.member.id, transition.after_channel_id
            )

    def close_all_open(self, guild_id: int, ended_at: datetime) -> int:
        return participation_repo.close_all_open_voice_sessions(guild_id, ended_at)

    def open_session(self, guild_id: int, member: MemberLike, channel_id: int, started_at: datetime) -> bool:
        if not is_eligible(member, self.settings):
            return False
        return participation_repo.open_voice_session(guild_id, member.id, channel_id, started_at)
