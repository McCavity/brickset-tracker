"""After a successful merlinssteine scrape, the (brand, slug) pair is
auto-persisted to brand_slugs via ensure_brand_slug. New brands whose
name IS the slug end up visible in /settings/brand-slugs automatically."""
import httpx
import pytest

from execution import scraper, brand_slugs
from navigation import lookup_router


class _FakeResponse:
    def __init__(self, html: str, status: int = 200):
        self.text = html
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _FakeClient:
    _html: str = ""
    def __init__(self, *args, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    async def get(self, url, headers=None, follow_redirects=True):
        return _FakeResponse(_FakeClient._html)


_HTML_SUCCESS = """
<html><body>
<h1>Ikea - Some Item | Set 99999</h1>
<h2>Details</h2>
<ul>
  <li>Von: Ikea</li>
  <li>Setnummer: 99999</li>
</ul>
<ul><li>500 Teile</li></ul>
</body></html>
"""


@pytest.fixture
def fake_scrape(monkeypatch, db):
    _FakeClient._html = _HTML_SUCCESS
    monkeypatch.setattr(scraper.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(scraper, "check_quota", lambda svc: True)
    monkeypatch.setattr(scraper, "increment_quota", lambda svc: None)


async def test_successful_scrape_auto_populates_brand_slugs(fake_scrape):
    """A brand the scraper hasn't seen before becomes visible in brand_slugs
    after a successful lookup."""
    # Confirm "Ikea" is NOT in brand_slugs initially
    assert "ikea" not in {r["brand"] for r in brand_slugs.list_brand_slugs()}

    result = await lookup_router._flow1(brand="Ikea", set_number="99999")
    assert result["status"] == "success"

    # Now "ikea" SHOULD be in the table with the fallback-derived slug "ikea"
    pairs = {r["brand"]: r["slug"] for r in brand_slugs.list_brand_slugs()}
    assert "ikea" in pairs
    assert pairs["ikea"] == "ikea"


async def test_successful_scrape_does_not_overwrite_existing_slug(fake_scrape):
    """If the brand is already mapped, ensure_brand_slug leaves it alone."""
    # Seed a custom mapping
    brand_slugs.add_brand_slug("CustomBrand", "custom-existing-slug")
    # Run the scrape — slug computed for CustomBrand would be "custombrand" (fallback)
    await lookup_router._flow1(brand="CustomBrand", set_number="12345")
    # The existing slug must NOT be overwritten
    assert brand_slugs.brand_to_slug("custombrand") == "custom-existing-slug"
