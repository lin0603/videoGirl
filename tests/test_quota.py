"""Tests for task #16: per-user quota and backpressure."""
from unittest.mock import AsyncMock, patch


async def _fake_redis(state: dict):
    """Return a fake Redis with in-memory state."""
    r = AsyncMock()

    async def fake_get(key):
        return state.get(key)

    async def fake_llen(key):
        return state.get(key, 0)

    pipe_mock = AsyncMock()

    async def fake_incr(key):
        state[key] = state.get(key, 0) + 1
        return state[key]

    async def fake_expire(key, ttl):
        pass

    async def fake_pipe_execute():
        return []

    pipe_mock.incr = fake_incr
    pipe_mock.expire = fake_expire
    pipe_mock.execute = fake_pipe_execute

    r.get = fake_get
    r.llen = fake_llen
    r.pipeline = lambda: pipe_mock

    return r


async def test_quota_allowed_when_under_limit() -> None:
    from shared.quota import check_quota
    state = {"media:quota:1001:image": "3"}
    with patch("shared.quota.get_redis", return_value=AsyncMock(side_effect=lambda: _fake_redis(state))):
        # Under default free limit of 10
        r = await _fake_redis(state)
        with patch("shared.quota.get_redis", new=AsyncMock(return_value=r)):
            result = await check_quota(1001, "image")
    assert result.allowed


async def test_quota_blocked_at_limit() -> None:
    from shared.quota import check_quota

    async def make_redis():
        state = {"media:quota:1001:image": "10"}  # exactly at free limit
        r = AsyncMock()
        r.get = AsyncMock(return_value="10")
        return r

    with patch("shared.quota.get_redis", new=AsyncMock(return_value=await make_redis())):
        result = await check_quota(1001, "image")
    assert not result.allowed
    assert result.reason is not None
    assert "上限" in result.reason


async def test_quota_vip_has_higher_limit() -> None:
    from shared.quota import check_quota

    # VIP limit for image is 50; at 25 should be allowed
    async def make_redis():
        r = AsyncMock()
        r.get = AsyncMock(return_value="25")
        return r

    with patch("shared.quota.get_redis", new=AsyncMock(return_value=await make_redis())):
        result = await check_quota(1001, "image", vip=True)
    assert result.allowed


async def test_backpressure_blocked_when_queue_full() -> None:
    from shared.quota import check_queue_backpressure

    async def make_redis():
        r = AsyncMock()
        r.llen = AsyncMock(return_value=5)  # at limit
        return r

    with patch("shared.quota.get_redis", new=AsyncMock(return_value=await make_redis())):
        result = await check_queue_backpressure()
    assert not result.allowed
    assert result.reason is not None


async def test_backpressure_allowed_when_queue_empty() -> None:
    from shared.quota import check_queue_backpressure

    async def make_redis():
        r = AsyncMock()
        r.llen = AsyncMock(return_value=2)
        return r

    with patch("shared.quota.get_redis", new=AsyncMock(return_value=await make_redis())):
        result = await check_queue_backpressure()
    assert result.allowed


async def test_quota_fails_open_on_redis_error() -> None:
    """Quota check must allow requests when Redis is unavailable."""
    from shared.quota import check_quota

    async def broken_redis():
        raise ConnectionError("redis down")

    with patch("shared.quota.get_redis", side_effect=broken_redis):
        result = await check_quota(1001, "video")
    assert result.allowed


async def test_increment_quota() -> None:
    from unittest.mock import MagicMock
    from shared.quota import increment_quota

    calls = []
    # Pipeline incr/expire are synchronous (not awaited), but execute is async.
    pipe_mock = MagicMock()
    pipe_mock.incr = MagicMock(side_effect=lambda k: calls.append(("incr", k)))
    pipe_mock.expire = MagicMock(side_effect=lambda k, t: calls.append(("expire", k, t)))
    pipe_mock.execute = AsyncMock(return_value=[])

    r = AsyncMock()
    r.pipeline = lambda: pipe_mock

    with patch("shared.quota.get_redis", new=AsyncMock(return_value=r)):
        await increment_quota(1001, "image")

    assert any(c[0] == "incr" and "1001" in c[1] and "image" in c[1] for c in calls)
