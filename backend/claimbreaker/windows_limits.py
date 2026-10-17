"""Windows parser job: enforce memory/CPU/process limits and kill on handle close."""

import os


def parser_job(pid, memory=1024**3):
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes as w

    size = ctypes.c_size_t

    class Basic(ctypes.Structure):
        _fields_ = [
            ("ProcessTime", ctypes.c_longlong),
            ("JobTime", ctypes.c_longlong),
            ("Flags", w.DWORD),
            ("MinWorking", size),
            ("MaxWorking", size),
            ("Processes", w.DWORD),
            ("Affinity", size),
            ("Priority", w.DWORD),
            ("Scheduling", w.DWORD),
        ]

    class IO(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")
        ]

    class Limits(ctypes.Structure):
        _fields_ = [
            ("Basic", Basic),
            ("IO", IO),
            ("ProcessMemory", size),
            ("JobMemory", size),
            ("PeakProcess", size),
            ("PeakJob", size),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    kernel.CreateJobObjectW.restype = w.HANDLE
    kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    kernel.SetInformationJobObject.restype = w.BOOL
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    kernel.AssignProcessToJobObject.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.CloseHandle.restype = w.BOOL
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limits = Limits()
        limits.Basic.Flags = (
            0x100 | 0x2000 | 0x2 | 0x8
        )  # process memory, kill-on-close, user CPU time, active process count
        limits.Basic.ProcessTime = 30 * 10_000_000
        limits.Basic.Processes = 4
        limits.ProcessMemory = memory
        if not kernel.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        process = kernel.OpenProcess(0x100 | 0x1, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel.AssignProcessToJobObject(handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(process)
    except BaseException:
        kernel.CloseHandle(handle)
        raise

    class Job:
        def close(self):
            nonlocal handle
            if handle:
                kernel.CloseHandle(handle)
                handle = None

    return Job()
