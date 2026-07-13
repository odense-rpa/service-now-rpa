import pytest

from snow import Driftsstatus, RpaClient, RpaProcess
from snow.rpa import RPA_PARENT_SYS_ID

from conftest import RPA_RECORD


def test_requires_credentials_or_client():
    with pytest.raises(ValueError):
        RpaClient()


def test_get_by_number_scopes_to_rpa_parent(rpa, fake):
    proc = rpa.get("BSN0009999")
    assert proc.name == "Testproces"
    query = fake.requests[-1].url.params["sysparm_query"]
    assert query == f"parent={RPA_PARENT_SYS_ID}^number=BSN0009999"


def test_get_by_sys_id_and_name(rpa):
    assert rpa.get(RPA_RECORD["sys_id"]).number == "BSN0009999"
    assert rpa.get("Testproces").number == "BSN0009999"


def test_get_unknown_raises_lookup_error(rpa):
    with pytest.raises(LookupError):
        rpa.get("BSN0000000")


def test_get_refuses_records_outside_rpa_parent(rpa, fake):
    outside = dict(RPA_RECORD, sys_id="f" * 32, number="BSN0000042", parent="andet-parent")
    fake.records[outside["sys_id"]] = outside
    with pytest.raises(LookupError):
        rpa.get("BSN0000042")


def test_save_patches_only_dirty_fields(rpa, fake):
    proc = rpa.get("BSN0009999")
    proc.comments = "opdateret"
    payload = rpa.save(proc)
    assert payload == {"comments": "opdateret"}
    assert fake.requests[-1].method == "PATCH"
    assert fake.records[proc.sys_id]["comments"] == "opdateret"
    # model refreshed and clean again
    assert proc.dirty_payload() == {}


def test_save_dry_run_writes_nothing(rpa, fake):
    proc = rpa.get("BSN0009999")
    proc.comments = "kun en test"
    payload = rpa.save(proc, dry_run=True)
    assert payload == {"comments": "kun en test"}
    assert all(r.method != "PATCH" for r in fake.requests)
    assert fake.records[proc.sys_id]["comments"] == ""


def test_save_with_no_changes_is_a_no_op(rpa, fake):
    proc = rpa.get("BSN0009999")
    requests_before = len(fake.requests)
    assert rpa.save(proc) == {}
    assert len(fake.requests) == requests_before


def test_save_refuses_foreign_parent(rpa):
    proc = RpaProcess.from_api(dict(RPA_RECORD, parent="andet-parent"))
    proc.comments = "x"
    with pytest.raises(PermissionError):
        rpa.save(proc)


def test_create_sets_rpa_parent(rpa, fake):
    new = rpa.create(RpaProcess(name="Ny proces", driftsstatus=Driftsstatus.UNDER_UDVIKLING))
    assert new.number == "BSN0010000"
    import json

    body = json.loads(fake.requests[-1].content)
    assert body["parent"] == RPA_PARENT_SYS_ID
    assert body["u_driftsstatus"] == "Under udvikling"


def test_create_requires_name_and_no_sys_id(rpa):
    with pytest.raises(ValueError):
        rpa.create(RpaProcess())
    with pytest.raises(ValueError):
        rpa.create(RpaProcess.from_api(RPA_RECORD))


def test_find_user_by_email_and_name(rpa):
    user = rpa.find_user("ana@odense.dk")
    assert user.name == "Anna Andersen"
    assert rpa.find_user("Anna Andersen").sys_id == user.sys_id
    assert rpa.find_user(user.sys_id).email == "ana@odense.dk"


def test_find_user_ambiguous_or_missing(rpa):
    with pytest.raises(LookupError, match="more than one"):
        rpa.find_user("Bo Berg")  # two users share this name
    with pytest.raises(LookupError, match="No active user"):
        rpa.find_user("findes-ikke@odense.dk")


def test_procesejer_is_writable_as_owned_by(rpa, fake):
    proc = rpa.get("BSN0009999")
    assert proc.procesejer == "aaaa1111aaaa1111aaaa1111aaaa1111"
    proc.procesejer = rpa.find_user("bob@odense.dk")  # User object accepted directly
    payload = rpa.save(proc)
    assert payload == {"owned_by": "bbbb2222bbbb2222bbbb2222bbbb2222"}
    assert fake.records[proc.sys_id]["owned_by"] == "bbbb2222bbbb2222bbbb2222bbbb2222"


def test_create_dry_run_writes_nothing(rpa, fake):
    requests_before = len(fake.requests)
    rpa.create(RpaProcess(name="Ny proces"), dry_run=True)
    assert len(fake.requests) == requests_before
