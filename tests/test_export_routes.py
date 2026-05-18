"""GET /api/export/json and /api/export/csv dump the full collection
with proper Content-Disposition headers and date-stamped filenames."""
import csv
import io
import json
from datetime import date

from fastapi.testclient import TestClient

from execution.db import get_connection
from tests.factories import make_set


def _set_web_images(set_id, urls):
    """Helper: write a list of URLs to the web_images column (stored as JSON)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sets SET web_images=? WHERE id=?",
            (json.dumps(urls), set_id),
        )


def test_export_json_returns_attachment_header(db):
    from main import app
    make_set(brand="LEGO", set_number="10298", name="Vespa 125", part_count=1106)

    with TestClient(app) as client:
        r = client.get("/api/export/json")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    today = date.today().isoformat()
    assert f'filename="brickset-tracker-{today}.json"' in r.headers["content-disposition"]
    assert r.headers["content-disposition"].startswith("attachment;")


def test_export_json_includes_all_sets(db):
    from main import app
    make_set(brand="LEGO",    set_number="10298", name="Vespa 125",   part_count=1106)
    make_set(brand="Cobi",    set_number="2999",  name="P-51 Mustang", part_count=265)
    make_set(brand="Pantasy", set_number="85036", name="Ape Logos",   part_count=300)

    with TestClient(app) as client:
        r = client.get("/api/export/json")

    rows = json.loads(r.text)
    assert isinstance(rows, list)
    assert len(rows) == 3
    brands = sorted(row["brand"] for row in rows)
    assert brands == ["Cobi", "LEGO", "Pantasy"]


def test_export_json_serialises_nested_fields_as_arrays(db):
    from main import app
    set_id = make_set(brand="LEGO", set_number="10298", name="Vespa", part_count=1106)
    _set_web_images(set_id, ["http://example.com/a.jpg", "http://example.com/b.jpg"])

    with TestClient(app) as client:
        r = client.get("/api/export/json")

    rows = json.loads(r.text)
    target = next(row for row in rows if row["id"] == set_id)
    assert target["web_images"] == ["http://example.com/a.jpg", "http://example.com/b.jpg"]
    # NOT a string — must be a real list.
    assert isinstance(target["web_images"], list)


def test_export_csv_returns_attachment_with_bom(db):
    from main import app
    make_set(brand="LEGO", set_number="10298", name="Vespa", part_count=1106)

    with TestClient(app) as client:
        r = client.get("/api/export/csv")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    today = date.today().isoformat()
    assert f'filename="brickset-tracker-{today}.csv"' in r.headers["content-disposition"]
    # UTF-8 BOM at the very start so Excel detects encoding correctly.
    assert r.content.startswith(b"\xef\xbb\xbf")


def test_export_csv_serialises_nested_fields_as_pipes(db):
    from main import app
    set_id = make_set(brand="LEGO", set_number="10298", name="Vespa", part_count=1106)
    _set_web_images(set_id, ["http://example.com/a.jpg", "http://example.com/b.jpg"])

    with TestClient(app) as client:
        r = client.get("/api/export/csv")

    # utf-8-sig strips the BOM during decode.
    text = r.content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    target = next(row for row in rows if int(row["id"]) == set_id)
    assert target["web_images"] == "http://example.com/a.jpg|http://example.com/b.jpg"
