"""Memory the app would otherwise waste (polyglotic-hq project 136)."""

import subprocess
import sys

import pytest

PRIVATE_BYTES = """
import ctypes, ctypes.wintypes as wt
import polyglotic_desktop  # first, as every entry point has it
import numpy

class Counters(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in (
            "PeakWorkingSetSize WorkingSetSize QuotaPeakPagedPoolUsage "
            "QuotaPagedPoolUsage QuotaPeakNonPagedPoolUsage QuotaNonPagedPoolUsage "
            "PagefileUsage PeakPagefileUsage PrivateUsage"
        ).split()
    ]

kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
kernel32.GetCurrentProcess.restype = ctypes.c_void_p
psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.DWORD]
counters = Counters()
counters.cb = ctypes.sizeof(counters)
assert psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
print(counters.PrivateUsage)
"""


@pytest.mark.windows_only  # Windows' process counters
def test_numpy_does_not_reserve_a_blas_buffer_per_cpu() -> None:
    """OpenBLAS reserves about 30 MB per CPU thread as numpy loads (480 MB
    on a 16-thread PC) unless told to use one thread, which the package
    does on import: Python with numpy stays under 60 MB of private memory
    (about 15 MB measured 2026-11-07)."""
    done = subprocess.run(
        [sys.executable, "-c", PRIVATE_BYTES],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    private_mb = int(done.stdout.strip()) / 2**20
    assert private_mb < 60, f"{private_mb:.0f} MB private after importing numpy"
