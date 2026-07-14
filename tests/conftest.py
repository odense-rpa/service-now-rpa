import json

import httpx
import pytest

from snow import RpaClient, ServiceNowClient
from snow.rpa import RPA_PARENT_SYS_ID

RPA_RECORD = {
    "sys_id": "abc123abc123abc123abc123abc123ab",
    "number": "BSN0009999",
    "parent": RPA_PARENT_SYS_ID,
    "sys_created_on": "2024-03-01 08:15:00",
    "sys_created_by": "ana@odense.dk",
    "sys_updated_on": "2026-06-30 14:02:11",
    "sys_updated_by": "bob@odense.dk",
    "name": "Testproces",
    "owned_by": "aaaa1111aaaa1111aaaa1111aaaa1111",
    "description": "",
    "comments": "",
    "start_date": "",
    "end_date": "",
    "u_driftsstatus": "I drift",
    "u_forvaltning": "Borgmesterforvaltningen",
    "u_frekvens": "",
    "u_procesid": "",
    "u_arbejdsgangsid": "",
    "u_procestid_minutter": "",
    "u_udbetaling": "Nej",
    "u_findes_der_persondata_i_rpa_processen": "Ja",
    "u_personf_lsomhed_i_de_indsamlede_data": "",
    "u_persontyper_i_de_indsamlede_data": "",
    "u_fagspecialister": "",
    "u_fagsuperbruger": "",
    "u_proceskonsulent": "",
    "u_udviklet_af": "",
    "u_it_system": "",
    "u_sbsyslink": "",
    "u_yderligere_integrationer": "",
}

USERS = [
    {"sys_id": "aaaa1111aaaa1111aaaa1111aaaa1111", "name": "Anna Andersen", "email": "ana@odense.dk", "active": "true"},
    {"sys_id": "bbbb2222bbbb2222bbbb2222bbbb2222", "name": "Bo Berg", "email": "bob@odense.dk", "active": "true"},
    {"sys_id": "cccc3333cccc3333cccc3333cccc3333", "name": "Bo Berg", "email": "bob2@odense.dk", "active": "true"},
]


class FakeServiceNow:
    """In-memory stand-in for the ServiceNow Table API, driven by MockTransport."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_requests = 0
        self.fail_next_with_401 = False
        self.records = {RPA_RECORD["sys_id"]: dict(RPA_RECORD)}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/oauth_token.do":
            self.token_requests += 1
            return httpx.Response(
                200, json={"access_token": f"tok-{self.token_requests}", "expires_in": 1799}
            )
        if self.fail_next_with_401:
            self.fail_next_with_401 = False
            return httpx.Response(401, json={"error": {"message": "unauthorized"}})
        assert request.headers["Authorization"].startswith("Bearer tok-")

        if request.method == "GET" and request.url.path == "/api/now/table/sys_user":
            query = request.url.params.get("sysparm_query", "")
            matches = [u for u in USERS if self._matches(u, query)]
            return httpx.Response(200, json={"result": matches})

        if request.method == "GET" and request.url.path == "/api/now/table/service_offering":
            query = request.url.params.get("sysparm_query", "")
            matches = [r for r in self.records.values() if self._matches(r, query)]
            offset = int(request.url.params.get("sysparm_offset", 0))
            limit = int(request.url.params.get("sysparm_limit", 100))
            return httpx.Response(200, json={"result": matches[offset : offset + limit]})

        if request.method == "PATCH":
            sys_id = request.url.path.rsplit("/", 1)[-1]
            self.records[sys_id].update(json.loads(request.content))
            return httpx.Response(200, json={"result": self.records[sys_id]})

        if request.method == "POST" and request.url.path == "/api/now/table/service_offering":
            body = json.loads(request.content)
            record = dict(RPA_RECORD) | body | {"sys_id": "new0" * 8, "number": "BSN0010000"}
            self.records[record["sys_id"]] = record
            return httpx.Response(201, json={"result": record})

        return httpx.Response(404, json={"error": {"message": f"no route for {request.url.path}"}})

    @staticmethod
    def _matches(record: dict, query: str) -> bool:
        for term in query.split("^"):
            if not term:
                continue
            if "LIKE" in term:
                field, value = term.split("LIKE", 1)
                if value.lower() not in str(record.get(field, "")).lower():
                    return False
            else:
                field, value = term.split("=", 1)
                if str(record.get(field, "")) != value:
                    return False
        return True


@pytest.fixture
def fake() -> FakeServiceNow:
    return FakeServiceNow()


@pytest.fixture
def sn(fake: FakeServiceNow) -> ServiceNowClient:
    return ServiceNowClient("test-id", "test-secret", scope="RPA 1", transport=fake.transport())


@pytest.fixture
def rpa(sn: ServiceNowClient) -> RpaClient:
    return RpaClient(client=sn)
