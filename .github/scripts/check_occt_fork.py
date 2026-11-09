# SPDX-License-Identifier: LGPL-2.1-or-later
"""
check_occt_fork.py

Run with FreeCADCmd: FreeCADCmd .github/scripts/check_occt_fork.py

Fails (exit code 1) unless the OCCT that FreeCAD's Part module has loaded is the AstoCAD OCCT
fork (https://github.com/AstoCAD/OCCT). A build that silently picked up upstream OCCT (from
conda-forge, a distribution or a stock LibPack) compiles and mostly passes the tests, so this is
checked at run time on the library the process really uses.

Marker: the fork's TKBRep exports the C function SetFuncShowTopoShape, which upstream OCCT does
not have. Part.OCC_VERSION is printed for the log only: it comes from the headers FreeCAD was
compiled against and is 8.0.1 for both.
"""

import ctypes
import os
import sys

import Part

MARKER = "SetFuncShowTopoShape"


def loaded_tkbrep():
    """Return (path, ctypes library) of the TKBRep the process has loaded, or (None, None)."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel32.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
        handle = kernel32.GetModuleHandleW("TKBRep.dll")  # never loads, only looks up
        if not handle:
            return None, None
        buf = ctypes.create_unicode_buffer(32768)
        kernel32.GetModuleFileNameW(handle, buf, len(buf))
        return buf.value, ctypes.WinDLL(buf.value)

    def is_tkbrep(path):
        return os.path.basename(path).startswith("libTKBRep.")

    paths = []
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None)
        libc._dyld_image_count.restype = ctypes.c_uint32
        libc._dyld_get_image_name.restype = ctypes.c_char_p
        libc._dyld_get_image_name.argtypes = [ctypes.c_uint32]
        for i in range(libc._dyld_image_count()):
            name = libc._dyld_get_image_name(i)
            if name:
                paths.append(os.fsdecode(name))
    else:
        with open("/proc/self/maps", encoding="utf-8", errors="replace") as maps:
            for line in maps:
                fields = line.split(None, 5)
                if len(fields) == 6:
                    paths.append(fields[5].strip())
    for path in paths:
        if is_tkbrep(path):
            # The library is already loaded: this returns the same handle, it loads nothing new.
            return path, ctypes.CDLL(path)
    return None, None


def main():
    print(f"Part.OCC_VERSION (compile time): {Part.OCC_VERSION}")
    Part.makeBox(1, 1, 1).isValid()  # make sure the OCCT libraries are in use
    path, lib = loaded_tkbrep()
    if lib is None:
        print("OCCT fork check FAILED: TKBRep is not loaded in this process")
        return 1
    print(f"TKBRep loaded from: {path}")
    if not hasattr(lib, MARKER):
        print(f"OCCT fork check FAILED: {MARKER} not exported, this is upstream OCCT")
        return 1
    print("OCCT fork check: OK (AstoCAD OCCT fork)")
    return 0


code = main()
# FreeCADCmd ends the process on SystemExit without finalizing Python: flush the output first.
sys.stdout.flush()
sys.exit(code)
