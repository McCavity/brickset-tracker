"""F1 — Brickset preview must not allow </script> injection via set names."""
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def _malicious_owned_collection():
    return {
        "status": "ok",
        "sets": [{
            "set_number": "10298",
            "set_id":     23456,
            # Crafted name: closing the script tag would let HTML escape.
            "name":       "Vespa </script><script>alert(1)</script>",
            "pieces":     1106,
            "theme":      "Creator Expert",
            "year":       2022,
            "ean":        None,
            "image_url":  None,
            "qty_owned":  1,
        }],
    }


def test_preview_escapes_script_terminator_in_payload(db):
    from main import app
    with patch("execution.brickset.fetch_owned_collection",
               new=AsyncMock(return_value=_malicious_owned_collection())):
        with TestClient(app) as client:
            r = client.post("/api/import/brickset/fetch")

    assert r.status_code == 200
    html = r.text
    # The raw </script> substring must NOT appear anywhere inside the
    # rendered payload (Jinja's tojson escapes < as <).
    # We sanity-check both: the escaped form appears, the raw form does not
    # appear inside a <script> block.
    assert "\\u003c/script\\u003e" in html or "\\u003c/script>" in html
    # The unescaped variant must not appear adjacent to the script-tag opening:
    assert "</script><script>alert(1)</script>" not in html
