"""Client library for the Odense ServiceNow instance.

For RPA developers: use RpaClient — it is scoped to RPA processes only.
"""

from .client import ServiceNowClient, ServiceNowError
from .rpa import (
    Driftsstatus,
    Forvaltning,
    Frekvens,
    Personoplysning,
    Persontype,
    RpaClient,
    RpaProcess,
    User,
)
from .settings import Settings

__all__ = [
    "Driftsstatus",
    "Forvaltning",
    "Frekvens",
    "Personoplysning",
    "Persontype",
    "RpaClient",
    "RpaProcess",
    "ServiceNowClient",
    "ServiceNowError",
    "Settings",
    "User",
]
