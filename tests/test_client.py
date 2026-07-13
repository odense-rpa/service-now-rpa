import pytest

from snow import ServiceNowError
from snow.rpa import RPA_PARENT_SYS_ID

from conftest import RPA_RECORD


def test_token_is_fetched_once_and_reused(sn, fake):
    sn.query("service_offering", limit=1)
    sn.query("service_offering", limit=1)
    assert fake.token_requests == 1


def test_token_request_body(sn, fake):
    sn.query("service_offering", limit=1)
    token_request = next(r for r in fake.requests if r.url.path == "/oauth_token.do")
    body = token_request.content.decode()
    assert "grant_type=client_credentials" in body
    assert "client_id=test-id" in body
    assert "scope=RPA+1" in body


def test_retries_once_with_fresh_token_on_401(sn, fake):
    sn.query("service_offering", limit=1)
    fake.fail_next_with_401 = True
    result = sn.query("service_offering", limit=1)
    assert result  # succeeded after retry
    assert fake.token_requests == 2


def test_query_builds_sysparm_params(sn, fake):
    sn.query("service_offering", query="number=BSN0009999", fields=["name", "number"], limit=7, offset=3)
    request = fake.requests[-1]
    params = request.url.params
    assert params["sysparm_query"] == "number=BSN0009999"
    assert params["sysparm_fields"] == "name,number"
    assert params["sysparm_limit"] == "7"
    assert params["sysparm_offset"] == "3"
    assert params["sysparm_exclude_reference_link"] == "true"


def test_query_all_paginates(sn, fake):
    for i in range(5):
        record = dict(RPA_RECORD, sys_id=f"{i:032x}", number=f"BSN{i:07}")
        fake.records[record["sys_id"]] = record
    del fake.records[RPA_RECORD["sys_id"]]
    rows = list(sn.query_all("service_offering", page_size=2))
    assert len(rows) == 5
    offsets = [r.url.params["sysparm_offset"] for r in fake.requests if r.method == "GET"]
    assert offsets == ["0", "2", "4"]


def test_error_response_raises(sn):
    with pytest.raises(ServiceNowError) as exc_info:
        sn.query("sys_choice")  # table the fake does not serve
    assert exc_info.value.status_code == 404
    assert "no route" in str(exc_info.value)


def test_update_record_sends_patch(sn, fake):
    sn.update_record("service_offering", RPA_RECORD["sys_id"], {"comments": "hej"})
    request = fake.requests[-1]
    assert request.method == "PATCH"
    assert request.url.path.endswith(RPA_RECORD["sys_id"])
    assert fake.records[RPA_RECORD["sys_id"]]["comments"] == "hej"


def test_create_record_sends_post(sn, fake):
    created = sn.create_record("service_offering", {"name": "Ny", "parent": RPA_PARENT_SYS_ID})
    request = fake.requests[-1]
    assert request.method == "POST"
    assert created["name"] == "Ny"
    assert created["number"] == "BSN0010000"
