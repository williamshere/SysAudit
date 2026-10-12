"""Installed-software inventory collector.

Reads the registry uninstall keys on Windows:
- HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall (64-bit view)
- HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall (32-bit)
- HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall (per-user)

Entries without a DisplayName or flagged as system components are skipped.
On non-Windows platforms the collector reports itself unavailable.
"""

import sys


def _read_uninstall_key(root, path):
    """Return a list of {name, version, publisher} dicts from one key."""
    import winreg  # noqa: PLC0415

    results = []
    try:
        key = winreg.OpenKey(root, path)
    except OSError:
        return results
    try:
        count = winreg.QueryInfoKey(key)[0]
        for i in range(count):
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                continue
            try:
                sk = winreg.OpenKey(key, sub)
            except OSError:
                continue
            try:

                def _val(name):
                    try:
                        v, _ = winreg.QueryValueEx(sk, name)
                        return v
                    except OSError:
                        return None

                name = _val("DisplayName")
                if not name:
                    continue
                if _val("SystemComponent") == 1:
                    continue
                # Skip bare KB hotfix entries; they add noise, not signal.
                if str(name).startswith("KB") and _val("Publisher") == "Microsoft Corporation":
                    continue
                results.append(
                    {
                        "name": str(name).strip(),
                        "version": str(_val("DisplayVersion") or "").strip() or None,
                        "publisher": str(_val("Publisher") or "").strip() or None,
                    }
                )
            finally:
                winreg.CloseKey(sk)
    finally:
        winreg.CloseKey(key)
    return results


def collect():
    if sys.platform != "win32":
        return {
            "available": False,
            "reason": "software inventory reads the Windows registry",
        }
    try:
        import winreg  # noqa: PLC0415
    except ImportError:
        return {"available": False, "reason": "winreg unavailable"}

    base = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    programs = []
    seen = set()
    for root, path in (
        (winreg.HKEY_LOCAL_MACHINE, base),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, base),
    ):
        try:
            for prog in _read_uninstall_key(root, path):
                key = (prog["name"], prog["version"])
                if key in seen:
                    continue
                seen.add(key)
                programs.append(prog)
        except Exception:
            continue

    programs.sort(key=lambda p: p["name"].lower())
    return {"available": True, "count": len(programs), "programs": programs}
