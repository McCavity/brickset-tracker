"""Scraper result dict uses 'list_price' (not 'price') for the
extracted Listenpreis. Verified by monkeypatching the HTTP layer
and feeding canned HTML."""
import httpx
import pytest

from execution import scraper


class _FakeResponse:
    def __init__(self, html: str, status: int = 200):
        self.text = html
        self.status_code = status
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _FakeClient:
    """Single-response fake httpx.AsyncClient."""
    _html: str = ""

    def __init__(self, *args, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def get(self, url, headers=None, follow_redirects=True):
        return _FakeResponse(_FakeClient._html)


_MINIMAL_HTML = """
<html><body>
<h1>LEGO 42171 — McLaren P1</h1>
<ul>
  <li>Marke: LEGO</li>
  <li>Setnummer: 42171</li>
  <li>Teile: 3893</li>
  <li>Thema: Technic</li>
  <li>Listenpreis: 449,99 EUR</li>
  <li>Erscheinungsjahr: 2023</li>
</ul>
</body></html>
"""


@pytest.fixture
def fake_scrape(monkeypatch, db):
    _FakeClient._html = _MINIMAL_HTML
    monkeypatch.setattr(scraper.httpx, "AsyncClient", _FakeClient)
    # Disable rate-limit check so the test is reproducible
    monkeypatch.setattr(scraper, "check_quota", lambda svc: True)
    monkeypatch.setattr(scraper, "increment_quota", lambda svc: None)


async def test_scrape_result_uses_list_price_key(fake_scrape):
    result = await scraper.scrape_set("lego", "42171")
    assert result["status"] == "success"
    assert "list_price" in result
    assert result["list_price"] == 449.99
    assert "price" not in result, "Old key 'price' should no longer be in the result"
