from __future__ import annotations

from datetime import timedelta

import pytest

from models import vip_voice


def test_role_cannot_be_reused_by_another_vip_channel() -> None:
    vip_voice.upsert_vip_channel(1, 10, 100)

    with pytest.raises(ValueError, match="only be assigned"):
        vip_voice.upsert_vip_channel(1, 20, 100)


def test_expired_request_is_marked_expired() -> None:
    request = vip_voice.create_request(1, 10, 50)
    assert [item.id for item in vip_voice.list_pending_requests(1, 10)] == [request.id]

    expired = vip_voice.expire_old_requests(request.expires_at + timedelta(seconds=1))

    assert expired == 1
    assert vip_voice.get_request(request.id).status == vip_voice.REQUEST_EXPIRED
    assert vip_voice.list_pending_requests(1, 10) == []
