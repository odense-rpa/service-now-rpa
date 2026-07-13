"""High-level client for RPA processes (service_offering records under "RPA Processer").

Designed for RPA developers: fetch a process, change attributes, save.
Only the fields changed are written back, and only whitelisted fields can be written.

    rpa = RpaClient(client_id=cred.username, client_secret=cred.password, scope="RPA 1")
    proc = rpa.get("BSN0002394")
    proc.driftsstatus = Driftsstatus.PAUSE
    proc.comments = "Pauset pga. ny SBSYS-version"
    rpa.save(proc)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar, Iterator

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

from .client import DEFAULT_INSTANCE, ServiceNowClient

TABLE = "service_offering"
# sys_id of the "RPA Processer" business service (cmdb_ci_service) all RPA processes hang under.
RPA_PARENT_SYS_ID = "076fdbd897dff11021cefda6f053af0f"


class Driftsstatus(StrEnum):
    I_DRIFT = "I drift"
    UDFASET = "Udfaset"
    PAUSE = "PT ikke i drift - sat på pause"
    UNDER_UDVIKLING = "Under udvikling"


class Forvaltning(StrEnum):
    BSF = "Beskæftigelses- og Socialforvaltningen"
    BMF = "Borgmesterforvaltningen"
    AEHF = "Ældre- og Handicapforvaltningen"
    SUF = "Sundhedsforvaltningen"
    BKF = "By- og Kulturforvaltningen"


class Personoplysning(StrEnum):
    """Kategorier af personoplysninger (values are the option sys_ids in ServiceNow)."""

    ALMINDELIGE_PERSONDATA = "54ce8357973e395021cefda6f053af03"  # Almindelige persondata jf. artikel 6
    CPR_NUMMER = "d9be0357973e395021cefda6f053aff0"  # CPR nummer jf. databeskyttelsesloven §11
    FOELSOMME_PERSONDATA = "0fce8357973e395021cefda6f053afd9"  # Følsomme persondata jf. artikel 9
    INGEN_PERSONDATA = "aeaec357973e395021cefda6f053afcb"  # Ingen persondata


class Persontype(StrEnum):
    """Kategorier af registrerede (values are the option sys_ids in ServiceNow)."""

    BORGERE = "15160ec3c365c654895fbaf4e401310e"
    BOERN = "85e586c3c365c654895fbaf4e401316b"
    EKSTERNE_SAMARBEJDSPARTNERE = "6e068ac3c365c654895fbaf4e4013111"
    MEDARBEJDERE = "80160e83c365c654895fbaf4e40131a6"
    SAERLIGT_UDSATTE = "a3f54ac3c365c654895fbaf4e4013129"


class Frekvens(StrEnum):
    # Values verified from live data (used by RDA processes). The full choice list
    # in ServiceNow may contain more (sys_choice is not readable with our OAuth scope);
    # extend this enum if the admin confirms additional values.
    UGENTLIGT = "Ugentligt"
    MAANEDLIGT = "Månedligt"
    AARLIGT = "Årligt"


class User(BaseModel):
    """A ServiceNow user (sys_user). Returned by RpaClient.find_user()."""

    sys_id: str
    name: str = ""
    email: str = ""
    active: bool = True


class RpaProcess(BaseModel):
    """One RPA process. Attribute names are Danish, matching the ServiceNow labels.

    Read-only identity fields have no alias-writes; everything in WRITABLE can be
    changed and saved via RpaClient.save().
    """

    model_config = ConfigDict(populate_by_name=True, validate_assignment=True, use_enum_values=False)

    # Identity (read-only)
    sys_id: str = ""
    number: str = ""
    parent: str = ""

    # Core info
    name: str = ""
    description: str = ""
    comments: str = ""
    start_date: str = ""
    end_date: str = ""

    # RPA fields (aliases are the ServiceNow column names)
    driftsstatus: Driftsstatus | None = None
    forvaltning: Forvaltning | None = None
    frekvens: Frekvens | None = None
    procesid: str = ""
    arbejdsgangsid: str = ""
    procestid_minutter: str = ""
    udbetaling: bool | None = None
    persondata_i_processen: bool | None = None
    # Multi-selects (lists of sys_ids; assignments accept Personoplysning/Persontype/User members).
    # Assign a new list to change them — in-place .append() is not tracked by save().
    personoplysninger: list[str] = Field(default_factory=list)
    persontyper: list[str] = Field(default_factory=list)
    fagspecialister: list[str] = Field(default_factory=list)
    # User references (sys_user sys_ids; assignments also accept a User object)
    procesejer: str = ""
    fagsuperbruger: str = ""
    proceskonsulent: str = ""
    udviklet_af: str = ""
    it_system: str = ""
    sbsyslink: str = ""
    yderligere_integrationer: str = ""

    _ALIASES: ClassVar[dict[str, str]] = {
        "driftsstatus": "u_driftsstatus",
        "forvaltning": "u_forvaltning",
        "frekvens": "u_frekvens",
        "procesid": "u_procesid",
        "arbejdsgangsid": "u_arbejdsgangsid",
        "procestid_minutter": "u_procestid_minutter",
        "udbetaling": "u_udbetaling",
        "persondata_i_processen": "u_findes_der_persondata_i_rpa_processen",
        "personoplysninger": "u_personf_lsomhed_i_de_indsamlede_data",
        "persontyper": "u_persontyper_i_de_indsamlede_data",
        "fagspecialister": "u_fagspecialister",
        "procesejer": "owned_by",
        "fagsuperbruger": "u_fagsuperbruger",
        "proceskonsulent": "u_proceskonsulent",
        "udviklet_af": "u_udviklet_af",
        "it_system": "u_it_system",
        "sbsyslink": "u_sbsyslink",
        "yderligere_integrationer": "u_yderligere_integrationer",
    }

    # Fields RPA developers may write. Everything else is read-only through this library.
    WRITABLE: ClassVar[set[str]] = {
        "name", "description", "comments", "start_date", "end_date",
        *_ALIASES,
    }

    _dirty: set[str] = PrivateAttr(default_factory=set)

    @field_validator("driftsstatus", "forvaltning", "frekvens", mode="before")
    @classmethod
    def _empty_to_none(cls, v: Any) -> Any:
        return None if v == "" else v

    @field_validator("procesejer", "fagsuperbruger", "proceskonsulent", "udviklet_af", mode="before")
    @classmethod
    def _user_to_sys_id(cls, v: Any) -> Any:
        return v.sys_id if isinstance(v, User) else v

    @field_validator("personoplysninger", "persontyper", "fagspecialister", mode="before")
    @classmethod
    def _glide_list(cls, v: Any) -> Any:
        # ServiceNow sends glide_lists as comma-joined sys_ids; accept User/enum members too.
        if v in ("", None):
            return []
        if isinstance(v, str):
            return v.split(",")
        return [item.sys_id if isinstance(item, User) else str(item) for item in v]

    @field_validator("it_system")
    @classmethod
    def _single_it_system(cls, v: str) -> str:
        # u_it_system is a single reference; ServiceNow silently drops everything
        # after the first value (verified live). Extra systems belong in
        # yderligere_integrationer.
        if "," in v:
            raise ValueError(
                "it_system holds exactly one system; put additional systems in yderligere_integrationer"
            )
        return v

    @field_validator("udbetaling", "persondata_i_processen", mode="before")
    @classmethod
    def _ja_nej_to_bool(cls, v: Any) -> Any:
        if v in ("", None):
            return None
        if isinstance(v, str):
            return v.strip().lower() == "ja"
        return v

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if name in type(self).model_fields:
            self._dirty.add(name)

    # --- (de)serialization ------------------------------------------------

    @classmethod
    def from_api(cls, record: dict[str, Any]) -> RpaProcess:
        data = {field: record.get(alias, "") for field, alias in cls._ALIASES.items()}
        for field in cls.model_fields:
            if field not in data:
                data[field] = record.get(field, "")
        proc = cls(**data)
        proc._dirty.clear()
        return proc

    @staticmethod
    def _to_api_value(value: Any) -> str:
        # Booleans map to the "Ja"/"Nej" choice values used by the u_* fields.
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Ja" if value else "Nej"
        if isinstance(value, list):
            return ",".join(value)
        if isinstance(value, StrEnum):
            return value.value
        return str(value)

    def dirty_payload(self) -> dict[str, str]:
        """API payload for changed, writable fields (column name -> value)."""
        payload = {}
        for field in self._dirty:
            if field in self.WRITABLE:
                alias = self._ALIASES.get(field, field)
                payload[alias] = self._to_api_value(getattr(self, field))
        return payload

    def full_payload(self) -> dict[str, str]:
        """API payload with every writable field that has a value (used for create)."""
        payload = {}
        for field in self.WRITABLE:
            value = getattr(self, field)
            if value not in ("", None) and value != []:
                alias = self._ALIASES.get(field, field)
                payload[alias] = self._to_api_value(value)
        return payload


_FETCH_FIELDS = sorted(
    {"sys_id", "number", "parent", *(RpaProcess._ALIASES.get(f, f) for f in RpaProcess.model_fields
      if f not in ("sys_id", "number", "parent"))}
)


class RpaClient:
    """Client for reading, updating and creating RPA processes.

    Hard-scoped to records under the "RPA Processer" service: it refuses to
    read or write anything else in the table.
    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        scope: str = "",
        instance: str = DEFAULT_INSTANCE,
        timeout: float = 30.0,
        client: ServiceNowClient | None = None,
    ):
        if client is not None:
            self._sn = client
        else:
            if not client_id or not client_secret:
                raise ValueError("RpaClient needs client_id and client_secret (or a ServiceNowClient via client=)")
            self._sn = ServiceNowClient(
                client_id, client_secret, scope=scope, instance=instance, timeout=timeout
            )

    @classmethod
    def from_env(cls, env_file: str = ".env") -> RpaClient:
        """Build a client from a .env file (dev and test use)."""
        return cls(client=ServiceNowClient.from_env(env_file))

    def close(self) -> None:
        self._sn.close()

    def __enter__(self) -> RpaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- reads ------------------------------------------------------------

    def get(self, key: str) -> RpaProcess:
        """Fetch one RPA process by number ("BSN0002394"), sys_id, or exact name."""
        if len(key) == 32 and all(ch in "0123456789abcdef" for ch in key):
            query = f"sys_id={key}"
        elif key.upper().startswith("BSN"):
            query = f"number={key}"
        else:
            query = f"name={key}"
        rows = self._sn.query(TABLE, query=f"parent={RPA_PARENT_SYS_ID}^{query}",
                              fields=_FETCH_FIELDS, limit=2)
        if not rows:
            raise LookupError(f"No RPA process matches {key!r} (is it under 'RPA Processer'?)")
        if len(rows) > 1:
            raise LookupError(f"{key!r} matches more than one RPA process; use its number or sys_id")
        return RpaProcess.from_api(rows[0])

    def list(
        self,
        *,
        driftsstatus: Driftsstatus | None = None,
        forvaltning: Forvaltning | None = None,
    ) -> Iterator[RpaProcess]:
        """Iterate all RPA processes, optionally filtered."""
        query = f"parent={RPA_PARENT_SYS_ID}"
        if driftsstatus:
            query += f"^u_driftsstatus={driftsstatus.value}"
        if forvaltning:
            query += f"^u_forvaltning={forvaltning.value}"
        for record in self._sn.query_all(TABLE, query=query, fields=_FETCH_FIELDS):
            yield RpaProcess.from_api(record)

    def search(self, text: str) -> list[RpaProcess]:
        """Find RPA processes whose name contains `text`."""
        rows = self._sn.query(TABLE, query=f"parent={RPA_PARENT_SYS_ID}^nameLIKE{text}",
                              fields=_FETCH_FIELDS, limit=100)
        return [RpaProcess.from_api(r) for r in rows]

    def find_user(self, key: str) -> User:
        """Find one active user by email, full name, or sys_id.

        The result can be assigned directly to the user fields:
            proc.proceskonsulent = rpa.find_user("clm@odense.dk")
        """
        if len(key) == 32 and all(ch in "0123456789abcdef" for ch in key):
            query = f"sys_id={key}"
        elif "@" in key:
            query = f"email={key}"
        else:
            query = f"name={key}"
        fields = ["sys_id", "name", "email", "active"]
        rows = self._sn.query("sys_user", query=f"{query}^active=true", fields=fields, limit=2)
        if not rows and "@" not in key:
            rows = self._sn.query("sys_user", query=f"nameLIKE{key}^active=true", fields=fields, limit=2)
        if not rows:
            raise LookupError(f"No active user matches {key!r}")
        if len(rows) > 1:
            raise LookupError(f"{key!r} matches more than one user; use their email or sys_id")
        return User.model_validate(rows[0])

    # --- writes -----------------------------------------------------------

    def save(self, proc: RpaProcess, *, dry_run: bool = False) -> dict[str, str]:
        """PATCH the changed fields of a process back to ServiceNow.

        Returns the payload that was (or with dry_run=True, would be) written.
        """
        if not proc.sys_id:
            raise ValueError("Process has no sys_id — use create() for new processes")
        if proc.parent != RPA_PARENT_SYS_ID:
            raise PermissionError(f"{proc.number or proc.sys_id} is not under 'RPA Processer'; refusing to write")
        payload = proc.dirty_payload()
        if not payload:
            return {}
        if dry_run:
            return payload
        updated = self._sn.update_record(TABLE, proc.sys_id, payload, fields=_FETCH_FIELDS)
        refreshed = RpaProcess.from_api(updated)
        for field in type(proc).model_fields:
            super(RpaProcess, proc).__setattr__(field, getattr(refreshed, field))
        proc._dirty.clear()
        return payload

    def create(self, proc: RpaProcess, *, dry_run: bool = False) -> RpaProcess:
        """Create a new RPA process under "RPA Processer".

        Build an RpaProcess(name=..., driftsstatus=..., ...) and pass it here.
        With dry_run=True nothing is written and the payload is returned unchanged
        on the input model (sys_id stays empty).
        """
        if not proc.name:
            raise ValueError("A new RPA process needs at least a name")
        if proc.sys_id:
            raise ValueError(f"Process already exists ({proc.number or proc.sys_id}); use save() instead")
        payload = proc.full_payload()
        payload["parent"] = RPA_PARENT_SYS_ID
        if dry_run:
            return proc
        created = self._sn.create_record(TABLE, payload, fields=_FETCH_FIELDS)
        return RpaProcess.from_api(created)
