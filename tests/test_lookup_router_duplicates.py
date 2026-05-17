"""S3 — route_lookup must surface a duplicates count when the user already
owns this brand+set_number, so the add page can warn them."""
import pytest
from unittest.mock import AsyncMock, patch

from tests.factories import make_set


async def test_duplicates_populated_when_set_already_owned(db):
    from navigation.lookup_router import route_lookup
    make_set(brand="LEGO", set_number="10298")
    make_set(brand="LEGO", set_number="10298")

    fake_scrape  = AsyncMock(return_value={"status": "success", "name": "Vespa"})
    fake_fetch   = AsyncMock(return_value={"status": "not_found"})

    with patch("navigation.lookup_router.scrape_set",  new=fake_scrape), \
         patch("navigation.lookup_router.fetch_set",   new=fake_fetch):
        result = await route_lookup(brand="LEGO", set_number="10298")

    assert result["status"] == "success"
    dupes = result["prefill"].get("duplicates") or []
    assert len(dupes) == 2


async def test_duplicates_absent_when_set_not_owned(db):
    from navigation.lookup_router import route_lookup
    # No make_set() calls — collection is empty.
    fake_scrape  = AsyncMock(return_value={"status": "success", "name": "Vespa"})
    fake_fetch   = AsyncMock(return_value={"status": "not_found"})

    with patch("navigation.lookup_router.scrape_set",  new=fake_scrape), \
         patch("navigation.lookup_router.fetch_set",   new=fake_fetch):
        result = await route_lookup(brand="LEGO", set_number="10298")

    assert result["status"] == "success"
    assert not result["prefill"].get("duplicates")
