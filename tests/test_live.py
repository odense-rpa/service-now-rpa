"""Read-only smoke tests against the live ServiceNow instance.

These run only when credentials are available (a .env file in the project root
or CLIENT_ID/CLIENT_SECRET in the environment); otherwise they skip.
Deselect explicitly with: pytest -m "not live"

They never write anything.
"""

import os
from pathlib import Path

import pytest

from snow import Driftsstatus, RpaClient, ServiceNowClient

# The documented, known-stable example record from the API handover.
EXAMPLE_SYS_ID = "52ad61f497368a5021cefda6f053afc9"

_ENV_FILE = Path(__file__).parent.parent / ".env"
_have_credentials = _ENV_FILE.exists() or "CLIENT_ID" in os.environ

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not _have_credentials, reason="no ServiceNow credentials available"),
]


def test_token_and_read_known_record():
    with ServiceNowClient.from_env(str(_ENV_FILE)) as sn:
        record = sn.get_record("service_offering", EXAMPLE_SYS_ID, fields=["sys_id", "name"])
    assert record["sys_id"] == EXAMPLE_SYS_ID
    assert record["name"] == "Generationspagten"


def test_rpa_client_reads_a_process():
    with RpaClient.from_env(str(_ENV_FILE)) as rpa:
        procs = rpa.search("Udrejsebreve")
        assert procs, "expected at least one RPA process matching 'Udrejsebreve'"
        proc = rpa.get(procs[0].number)
    assert proc.number.startswith("BSN")
    assert proc.driftsstatus is None or isinstance(proc.driftsstatus, Driftsstatus)
