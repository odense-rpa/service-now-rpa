import pytest
from pydantic import ValidationError

from snow import Driftsstatus, Forvaltning, Frekvens, RpaProcess

from conftest import RPA_RECORD


def test_from_api_parses_types():
    proc = RpaProcess.from_api(RPA_RECORD)
    assert proc.number == "BSN0009999"
    assert proc.driftsstatus is Driftsstatus.I_DRIFT
    assert proc.forvaltning is Forvaltning.BMF
    assert proc.udbetaling is False  # "Nej"
    assert proc.persondata_i_processen is True  # "Ja"
    assert proc.frekvens is None  # empty string -> None


def test_from_api_starts_clean():
    proc = RpaProcess.from_api(RPA_RECORD)
    assert proc.dirty_payload() == {}


def test_dirty_payload_contains_only_changed_fields():
    proc = RpaProcess.from_api(RPA_RECORD)
    proc.driftsstatus = Driftsstatus.PAUSE
    proc.comments = "test"
    assert proc.dirty_payload() == {
        "u_driftsstatus": "PT ikke i drift - sat på pause",
        "comments": "test",
    }


def test_non_writable_fields_never_reach_payload():
    proc = RpaProcess.from_api(RPA_RECORD)
    proc.number = "BSN0000001"  # tracked as dirty, but number is not writable
    proc.comments = "test"
    assert proc.dirty_payload() == {"comments": "test"}


def test_bools_serialize_as_ja_nej():
    proc = RpaProcess.from_api(RPA_RECORD)
    proc.udbetaling = True
    proc.persondata_i_processen = None
    payload = proc.dirty_payload()
    assert payload["u_udbetaling"] == "Ja"
    assert payload["u_findes_der_persondata_i_rpa_processen"] == ""


def test_invalid_choice_value_rejected():
    proc = RpaProcess.from_api(RPA_RECORD)
    with pytest.raises(ValidationError):
        proc.driftsstatus = "Hver anden torsdag"
    with pytest.raises(ValidationError):
        proc.frekvens = "Kvartalsvis"


def test_full_payload_skips_empty_fields():
    proc = RpaProcess(name="Ny proces", frekvens=Frekvens.MAANEDLIGT)
    assert proc.full_payload() == {"name": "Ny proces", "u_frekvens": "Månedligt"}
