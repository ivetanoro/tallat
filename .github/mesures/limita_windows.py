"""A Windows, engega una ordre amb la memòria i els processadors limitats de debò (un Job Object).
    python limita_windows.py MEMORIA_MB PROCESSADORS -- ordre...
"""
import ctypes
import subprocess
import sys
from ctypes import wintypes

JobObjectExtendedLimitInformation, JobObjectCpuRateControlInformation = 9, 15
LIMIT_JOB_MEMORY, LIMIT_KILL_ON_CLOSE = 0x200, 0x2000
CPU_ENABLE, CPU_HARD_CAP = 0x1, 0x4


class IO(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in ("a", "b", "c", "d", "e", "f")]


class Basica(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong), ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class Estesa(ctypes.Structure):
    _fields_ = [("Basic", Basica), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class Cpu(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


def main() -> int:
    memoria, processadors = int(sys.argv[1]), int(sys.argv[2])
    ordre = sys.argv[sys.argv.index("--") + 1:]
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.restype = wintypes.HANDLE
    k.GetCurrentProcess.restype = wintypes.HANDLE
    k.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    k.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    feina = k.CreateJobObjectW(None, None)
    e = Estesa()
    e.Basic.LimitFlags = LIMIT_JOB_MEMORY | LIMIT_KILL_ON_CLOSE
    e.JobMemoryLimit = memoria * 1024 * 1024
    if not k.SetInformationJobObject(feina, JobObjectExtendedLimitInformation, ctypes.byref(e), ctypes.sizeof(e)):
        sys.exit(f"memòria: {ctypes.get_last_error()}")
    import os
    c = Cpu(CPU_ENABLE | CPU_HARD_CAP, min(10000, int(10000 * processadors / (os.cpu_count() or 1))))
    if not k.SetInformationJobObject(feina, JobObjectCpuRateControlInformation, ctypes.byref(c), ctypes.sizeof(c)):
        sys.exit(f"processadors: {ctypes.get_last_error()}")
    if not k.AssignProcessToJobObject(feina, k.GetCurrentProcess()):
        sys.exit(f"assigna: {ctypes.get_last_error()}")
    r = subprocess.run(ordre).returncode
    k.QueryInformationJobObject(feina, JobObjectExtendedLimitInformation, ctypes.byref(e), ctypes.sizeof(e), None)
    print(f"@limitat memoria_max_mb={e.PeakJobMemoryUsed // (1024 * 1024)} limit_mb={memoria} processadors={processadors} sortida={r}")
    return r


if __name__ == "__main__":
    sys.exit(main())
