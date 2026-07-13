# snow

Python client library for the Odense ServiceNow instance, built for RPA
developers to read, update and create their RPA processes.

## Install

From a consuming project:

```
uv add git+https://github.com/odense-rpa/service-now-rpa.git
```

For development in this repo: `uv sync` (installs the library editable from `src/snow`).
Build distributables with `uv build`.

## Credentials

**Production** — pass credentials explicitly, e.g. from the automation-server
credential store (same pattern as the Nexus client):

```python
from automation_server_client import Credential
from snow import RpaClient

sn_cred = Credential.get_credential("ServiceNow")
rpa = RpaClient(
    client_id=sn_cred.username,
    client_secret=sn_cred.password,
    scope="RPA 1",
)
```

**Local development / tests** — `RpaClient.from_env()` reads a `.env` file
(git-ignored here):

```
CLIENT_ID=...
CLIENT_SECRET="..."
CLIENT_SCOPE="..."
INSTANCE_URL=...   # optional, defaults to https://odense.service-now.com
```

## RPA developers: use `RpaClient`

RPA processes are `service_offering` records under the "RPA Processer" service.
`RpaClient` is hard-scoped to those records — it cannot read or write anything
else in the table.

```python
from snow import RpaClient, RpaProcess, Driftsstatus, Forvaltning

with RpaClient.from_env() as rpa:   # or RpaClient(client_id=..., client_secret=..., scope=...)
    # Fetch by number, sys_id, or exact name
    proc = rpa.get("BSN0002394")

    # Change what you need — the library tracks exactly what you touched
    proc.driftsstatus = Driftsstatus.PAUSE
    proc.comments = "Pauset pga. ny SBSYS-version"
    proc.procestid_minutter = "12"

    # See what would be written…
    print(rpa.save(proc, dry_run=True))
    # …then write it. Only the changed fields are PATCHed.
    rpa.save(proc)

    # List / search
    for p in rpa.list(driftsstatus=Driftsstatus.I_DRIFT, forvaltning=Forvaltning.BSF):
        print(p.number, p.name)
    hits = rpa.search("faktura")

    # Create a new process (lands under "RPA Processer" automatically)
    new = rpa.create(RpaProcess(
        name="Min nye proces",
        driftsstatus=Driftsstatus.UNDER_UDVIKLING,
        forvaltning=Forvaltning.BMF,
        persondata_i_processen=True,
    ))
    print(new.number)  # BSN number assigned by ServiceNow
```

Field names are Danish, matching the ServiceNow labels (`driftsstatus`,
`forvaltning`, `proceskonsulent`, …). `udbetaling` and
`persondata_i_processen` are Python bools, stored as "Ja"/"Nej".

Safety rails, since this is the live instance:
- Only fields in `RpaProcess.WRITABLE` can be written (the `u_*` RPA fields,
  `name`, `description`, `comments`, dates). System/ownership/billing fields are read-only.
- `save()` writes only the fields you actually changed.
- `save(dry_run=True)` / `create(dry_run=True)` show what would happen without writing.
- Writes to records outside "RPA Processer" are refused.

## Low-level access: `ServiceNowClient`

```python
from snow import ServiceNowClient

with ServiceNowClient(client_id=..., client_secret=..., scope="RPA 1") as sn:
    record = sn.get_record("service_offering", "52ad61f4...")
    rows = sn.query("service_offering", query="nameLIKEpagt", fields=["name"], limit=10)
    for row in sn.query_all("service_offering", fields=["sys_id", "name"]):
        ...
```

OAuth token fetch/refresh is automatic (~30 min lifetime, refreshed early,
one retry on 401).

Run the demo: `uv run examples/demo.py`
