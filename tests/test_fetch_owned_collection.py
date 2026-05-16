"""fetch_owned_collection pages through Brickset getSets with owned=1
until fewer than pageSize results return. Each page consumes one
quota point. Test by replacing httpx.AsyncClient with a fake that
serves a canned sequence of responses."""
import json

import httpx
import pytest

from execution import brickset, rate_limit
from execution.brickset import fetch_owned_collection


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
    def json(self):
        return self._payload


class _FakeClient:
    """Replaces httpx.AsyncClient. Dispenses canned responses in order
    and records each POST it received."""
    _pages: list = []
    calls:   list = []

    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def post(self, url, data):
        _FakeClient.calls.append({"url": url, "data": data})
        if not _FakeClient._pages:
            return _FakeResponse({"status": "success", "sets": []})
        return _FakeResponse(_FakeClient._pages.pop(0))


@pytest.fixture
def fake_brickset(monkeypatch, db):
    """Patch httpx.AsyncClient in execution.brickset to use _FakeClient.

    The db fixture is included so quota tracking writes to the temp DB.
    Use _FakeClient.set_pages([...]) before calling fetch_owned_collection.
    """
    _FakeClient._pages = []
    _FakeClient.calls = []
    monkeypatch.setattr(brickset.httpx, "AsyncClient", _FakeClient)
    yield _FakeClient


def _set(set_number: str) -> dict:
    return {
        "setID": int(set_number.replace("-", "")[:6]),
        "number": set_number, "name": f"Set {set_number}",
        "pieces": 100, "theme": "Test", "year": 2024,
        "barcode": {}, "image": {},
        "collection": {"qtyOwned": 1},
    }


def _page(sets, status="success"):
    return {"status": status, "sets": sets}


async def test_single_page_under_size(fake_brickset):
    """One page with 30 sets exits cleanly with a single API call."""
    fake_brickset._pages = [_page([_set(f"100{i:02d}") for i in range(30)])]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 30
    assert len(fake_brickset.calls) == 1


async def test_pages_through_multiple_pages(fake_brickset):
    """130 sets total → page 1 = 100, page 2 = 30, exits."""
    fake_brickset._pages = [
        _page([_set(f"100{i:02d}") for i in range(100)]),
        _page([_set(f"200{i:02d}") for i in range(30)]),
    ]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 130
    assert len(fake_brickset.calls) == 2


async def test_exact_multiple_of_page_size_makes_one_extra_call(fake_brickset):
    """Exactly 100 sets → page 1 = 100, page 2 = 0, exits.
    The empty page counts as one quota point (acceptable edge case)."""
    fake_brickset._pages = [
        _page([_set(f"100{i:02d}") for i in range(100)]),
        _page([]),
    ]
    result = await fetch_owned_collection()
    assert result["status"] == "ok"
    assert len(result["sets"]) == 100
    assert len(fake_brickset.calls) == 2


async def test_brickset_returns_non_success(fake_brickset):
    fake_brickset._pages = [{"status": "invalidApiKey", "message": "Bad key"}]
    result = await fetch_owned_collection()
    assert result["status"] == "error"
    assert "Bad key" in (result.get("message") or "")


async def test_quota_exceeded_blocks_first_call(monkeypatch, fake_brickset):
    monkeypatch.setattr("execution.brickset.check_quota", lambda svc: False)
    result = await fetch_owned_collection()
    assert result["status"] == "quota_exceeded"
    assert len(fake_brickset.calls) == 0


async def test_payload_includes_owned_and_user_hash(fake_brickset):
    fake_brickset._pages = [_page([])]
    await fetch_owned_collection()
    posted = fake_brickset.calls[0]["data"]
    params = json.loads(posted["params"])
    assert params.get("owned") == 1
    assert "userHash" in posted
    assert "apiKey" in posted
