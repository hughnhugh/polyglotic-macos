"""Whether Windows calls the connection metered (decision 0122)."""

import sys

import pytest

if sys.platform != "win32":
    pytest.skip("Windows only", allow_module_level=True)

from polyglotic_desktop.platform.windows import network_cost


def test_a_capped_charged_over_or_roaming_connection_is_metered() -> None:
    assert not network_cost.metered_cost(network_cost.UNRESTRICTED)
    assert not network_cost.metered_cost(0)  # unknown: Windows' own default
    assert network_cost.metered_cost(network_cost.FIXED)
    assert network_cost.metered_cost(network_cost.VARIABLE)
    assert network_cost.metered_cost(network_cost.UNRESTRICTED | network_cost.ROAMING)
    assert network_cost.metered_cost(network_cost.FIXED | network_cost.OVER_DATA_LIMIT)


@pytest.mark.windows_only
def test_this_pcs_connection_is_read() -> None:
    assert network_cost.metered() in (True, False)
