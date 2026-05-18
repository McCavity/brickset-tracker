"""GET /add?clone_from=<id> pre-populates identity fields from an existing set,
leaving instance fields (condition, location, date, price, note, photos) blank."""
import json

from fastapi.testclient import TestClient

from execution.db import get_connection
from tests.factories import make_set


def _set_extra_fields(set_id, **fields):
    """Helper: update fields on an existing set that make_set doesn't accept directly."""
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with get_connection() as conn:
        conn.execute(f"UPDATE sets SET {cols} WHERE id=?", (*fields.values(), set_id))


def test_clone_from_populates_identity_fields(db):
    from main import app

    source = make_set(
        brand="LEGO", set_number="10298", name="Vespa 125",
        part_count=1106, theme="Creator Expert", release_year=2022,
        ean="5702016912661", brickset_set_id=23456, minifigs=0,
    )
    _set_extra_fields(source, web_images=json.dumps([
        "https://images.brickset.com/sets/large/10298-1.jpg",
        "https://images.brickset.com/sets/AdditionalImages/10298-1.jpg",
    ]))

    with TestClient(app) as client:
        r = client.get(f"/add?clone_from={source}")

    assert r.status_code == 200
    html = r.text
    # Identity fields should be in the form. Use value="..." pattern for inputs.
    assert 'value="LEGO"' in html
    assert 'value="10298"' in html
    assert "Vespa 125" in html  # name appears in value="..."
    assert 'value="1106"' in html  # part_count
    assert "Creator Expert" in html  # theme
    assert 'value="2022"' in html  # release_year
    assert "5702016912661" in html  # ean
    assert '"23456"' in html or 'value="23456"' in html  # brickset_set_id hidden input
    # web_images are serialized into a hidden JSON input (web_images_json).
    assert "10298-1.jpg" in html


def test_clone_from_skips_instance_fields(db):
    from main import app

    source = make_set(
        brand="LEGO", set_number="10298", name="Vespa 125",
        part_count=1106, condition="gebaut", location="Regal 5",
        date_of_purchase="2024-12-25", price_paid=99.95, list_price=109.99,
        note="Sentimental — first vintage build",
    )

    with TestClient(app) as client:
        r = client.get(f"/add?clone_from={source}")

    assert r.status_code == 200
    html = r.text
    # Instance fields must NOT appear in the form.
    assert "Sentimental" not in html
    assert "Regal 5" not in html
    assert "2024-12-25" not in html
    assert "99.95" not in html
    assert "109.99" not in html
    # Condition select shouldn't have "gebaut" pre-selected.
    # Look for the pattern that would mean it IS selected.
    assert 'value="gebaut" selected' not in html


def test_clone_from_invalid_id_falls_back_to_blank_add(db):
    """If clone_from points at a non-existent set, /add should render normally
    (no 404, no crash) — same as a regular blank /add page."""
    from main import app

    with TestClient(app) as client:
        r = client.get("/add?clone_from=99999")

    assert r.status_code == 200
    # Blank add page: no value="LEGO" or other pre-filled identity field.
    # (Brand is empty by default — the input has value="" or no value attribute.)
    assert "Vespa" not in r.text


def test_clone_html_escapes_web_images_json(db):
    """The web_images_json hidden input must HTML-escape its JSON value so the
    surrounding value="..." attribute doesn't terminate early on inner quotes.

    Regression: before the fix, the rendered HTML looked like
        value="["https://example.com/a.jpg"]"
    which the browser parses as value="["  with the rest as garbage attributes,
    so JSON.parse(input.value) throws "Unexpected end of input" and /api/sets
    POST submits a malformed payload that 500s on the server. End result: the
    cloned set couldn't be saved.
    """
    from main import app

    source = make_set(brand="LEGO", set_number="10298", name="Vespa", part_count=1106)
    _set_extra_fields(source, web_images=json.dumps([
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    ]))

    with TestClient(app) as client:
        r = client.get(f"/add?clone_from={source}")

    assert r.status_code == 200
    html = r.text
    # The hidden input's value attribute must contain HTML-escaped quotes
    # (&quot; or the numeric equivalent &#34;) — never raw `"` from the JSON output.
    # Find the full input element via a substring search.
    idx = html.find('id="web-images-json"')
    assert idx != -1, "web-images-json input must be present"
    # Slice forward to the closing > of that tag.
    tag_end = html.index('>', idx)
    input_html = html[idx:tag_end + 1]
    # Some escaped form must be present (Jinja uses numeric &#34; by default).
    assert '&quot;' in input_html or '&#34;' in input_html, (
        f"JSON quotes must be HTML-escaped; got: {input_html!r}"
    )
    # The raw form (a literal `"` adjacent to the URL) must NOT appear
    # inside the value="..." attribute.
    assert '"https://example.com' not in input_html, (
        f"Raw double-quote next to URL would break attribute parsing; got: {input_html!r}"
    )
    # Round-trip check: decode the value back and ensure it parses as JSON.
    import re, html as html_lib
    match = re.search(r'value="([^"]*)"', input_html)
    assert match, f"could not locate value=... in {input_html!r}"
    decoded = html_lib.unescape(match.group(1))
    parsed = json.loads(decoded)
    assert parsed == [
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    ]
