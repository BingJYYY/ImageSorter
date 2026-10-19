"""Patch PySide6\\Qt6Core.dll so its WinRT API set imports point to combase.dll.

Background
----------
Qt6Core.dll statically links two API set stub DLLs:
  - api-ms-win-core-winrt-l1-1-0.dll          -> RoGetActivationFactory
  - api-ms-win-core-winrt-error-l1-1-1.dll    -> RoOriginateLanguageException

On some Windows installations (notably Windows 11 Home China 10.0.26200
observed in the wild) these stub DLLs are missing from System32 even
though the underlying functions exist inside combase.dll. The Win32
loader then fails with ERROR_PROC_NOT_FOUND (winerror 127) ->
"DLL load failed" when Python imports PySide6.QtCore.

Fix
---
Rewrite the import-table entries so those two DLLs read "combase.dll".
The functions themselves live in combase.dll on every supported Windows,
so the loader will resolve them via the same exported names.

Implementation
--------------
The patch is applied with an in-place byte rewrite -- the file size and
PE layout stay identical, so PyInstaller can still extract the patched
copy from its CArchive at runtime without decompression errors.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

try:
    import pefile
except ImportError:
    print("[patch_qt6core] pefile not installed; skipping patch.", file=sys.stderr)
    sys.exit(0)


WANTED_API_STUBS = {
    "api-ms-win-core-winrt-l1-1-0.dll":        "combase.dll",
    "api-ms-win-core-winrt-error-l1-1-1.dll":  "combase.dll",
}


def _patch_bytes_in_place(qt6_path: Path) -> list[tuple[str, str]]:
    """Apply in-place byte patches to the import-table DLL names."""
    import traceback as _tb
    try:
        print(f"[patch_qt6core] reading {qt6_path}", flush=True)
        data = bytearray(qt6_path.read_bytes())
        print(f"[patch_qt6core] read {len(data):,} bytes", flush=True)
        print(f"[patch_qt6core] parsing PE", flush=True)
        pe = pefile.PE(str(qt6_path))
        print(f"[patch_qt6core] PE parsed", flush=True)
    except Exception:
        print(f"[patch_qt6core] parse error:", flush=True)
        _tb.print_exc()
        raise
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return []

    changes: list[tuple[str, str]] = []
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        name = entry.dll.decode() if isinstance(entry.dll, bytes) else entry.dll
        if name.lower() not in WANTED_API_STUBS:
            continue
        new_dll = WANTED_API_STUBS[name.lower()]
        if name.lower() == new_dll.lower():
            continue  # already patched

        # Sanity: new name must be <= old name so we can NUL-pad.
        if len(new_dll) > len(name):
            raise RuntimeError(
                f"Cannot shorten {name!r} -> {new_dll!r} in place"
            )

        # Find the file offset of the DLL name string.
        dll_rva = entry.struct.Name
        dll_offset = pe.get_offset_from_rva(dll_rva)
        old_in_file = data[dll_offset:dll_offset + len(name)].split(b"\x00", 1)[0]
        if old_in_file.decode("ascii", "replace").lower() == new_dll.lower():
            continue  # already patched by another process

        # Write the new name and NUL-pad to keep the same total length.
        new_bytes = new_dll.encode("ascii") + b"\x00" * (len(name) - len(new_dll))
        data[dll_offset:dll_offset + len(name)] = new_bytes
        changes.append((name, new_dll))

    if not changes:
        return []

    print(f"[patch_qt6core] writing patched {len(data):,} bytes", flush=True)
    try:
        qt6_path.write_bytes(bytes(data))
        print(f"[patch_qt6core] write ok", flush=True)
    except Exception:
        print(f"[patch_qt6core] write error:", flush=True)
        _tb.print_exc()
        raise
    return changes


def needs_patch(qt6_path: Path) -> bool:
    """Return True if Qt6Core.dll still has WinRT API stubs in its import table."""
    if not qt6_path.exists():
        return False
    pe = pefile.PE(str(qt6_path))
    if not hasattr(pe, "DIRECTORY_ENTRY_IMPORT"):
        return False
    for entry in pe.DIRECTORY_ENTRY_IMPORT:
        name = entry.dll.decode() if isinstance(entry.dll, bytes) else entry.dll
        if name.lower() in WANTED_API_STUBS:
            return True
    return False


def patch_qt6core(qt6_path: Path) -> list[tuple[str, str]]:
    """Rewrite WinRT API stub names to combase.dll in-place.

    The file size and layout stay identical so PyInstaller's CArchive
    extraction still works. Returns a list of (old, new) tuples for
    entries that were actually rewritten; empty if nothing to do.
    """
    if not qt6_path.exists():
        raise FileNotFoundError(qt6_path)

    return _patch_bytes_in_place(qt6_path)


def patch_frozen_qt6core() -> None:
    """Called from a PyInstaller-frozen main() to fix _MEIPASS\\PySide6\\Qt6Core.dll.

    Runs once per cold start; safe to call multiple times.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return  # not a frozen app
    candidate = Path(meipass) / "PySide6" / "Qt6Core.dll"
    if not candidate.exists():
        return  # PySide6 not bundled
    if not needs_patch(candidate):
        return  # already patched

    try:
        changes = patch_qt6core(candidate)
        if changes:
            print(f"[patch_qt6core] Patched: {candidate}")
            for old, new in changes:
                print(f"[patch_qt6core]   {old} -> {new}")
    except Exception as exc:
        print(f"[patch_qt6core] WARN: patch failed: {exc!r}", file=sys.stderr)


def main() -> int:
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
    else:
        target = Path(os.getcwd()) / ".venv" / "Lib" / "site-packages" / "PySide6" / "Qt6Core.dll"
    if not target.exists():
        print(f"Qt6Core.dll not found at: {target}", file=sys.stderr)
        return 1

    bak = target.with_suffix(".dll.bak")
    if not bak.exists():
        shutil.copy2(target, bak)
        print(f"Backup: {bak}")

    changes = patch_qt6core(target)
    print(f"\nQt6Core.dll checked at: {target}")
    if changes:
        for old, new in changes:
            print(f"  Patched {old} -> {new}")
    else:
        print("  No changes needed (already patched or fresh)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
