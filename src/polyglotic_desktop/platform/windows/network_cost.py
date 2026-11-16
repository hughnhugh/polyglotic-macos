"""Whether Windows calls this PC's connection metered - a phone's hotspot,
a capped plan, roaming - from the Network List Manager's cost
(`INetworkCostManager::GetCost`), through ctypes as `com.py` does. A
dictionary pack's download asks before it uses one (decision 0122).

Anything that can't be read counts as not metered: Windows' own default
for a connection whose cost it doesn't know, and a pack the learner asked
for isn't held back by a check that failed. Asked on the downloads'
thread; each thread joins COM once (`com.ensure_com`).
"""

import logging
from ctypes import POINTER, byref, c_void_p, wintypes

from polyglotic_desktop.platform.windows.com import (
    CLSCTX_ALL,
    GUID,
    ensure_com,
    method,
    ole32,
    release,
)

log = logging.getLogger(__name__)

CLSID_NETWORK_LIST_MANAGER = "{DCB00C01-570F-4A9B-8D69-199FDBA5723B}"
IID_NETWORK_COST_MANAGER = "{DCB00008-570F-4A9B-8D69-199FDBA5723B}"
GET_COST = 3  # INetworkCostManager's first method, after IUnknown's three

# NLM_CONNECTION_COST (netlistmgr.h)
UNRESTRICTED = 0x1
FIXED = 0x2
VARIABLE = 0x4
OVER_DATA_LIMIT = 0x10000
ROAMING = 0x40000


def metered_cost(cost: int) -> bool:
    """Whether a cost is one a download should ask about first: a plan
    with a cap or charged by use, over its limit, or roaming - as Windows'
    own "metered connection" means it."""
    return bool(cost & (FIXED | VARIABLE | OVER_DATA_LIMIT | ROAMING))


def metered() -> bool:
    """Whether the machine's connection is metered now (False if it can't
    be read)."""
    manager = c_void_p()
    try:
        ensure_com()
        result = ole32.CoCreateInstance(
            byref(GUID.parse(CLSID_NETWORK_LIST_MANAGER)),
            None,
            CLSCTX_ALL,
            byref(GUID.parse(IID_NETWORK_COST_MANAGER)),
            byref(manager),
        )
        if result < 0 or not manager:
            log.info("connection cost not read: %#x", result & 0xFFFFFFFF)
            return False
        cost = wintypes.DWORD()
        method(manager, GET_COST, POINTER(wintypes.DWORD), c_void_p)(byref(cost), None)
        return metered_cost(cost.value)
    except OSError as e:
        log.info("connection cost not read: %s", type(e).__name__)
        return False
    finally:
        if manager:
            release(manager)
