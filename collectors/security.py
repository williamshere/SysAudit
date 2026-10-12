"""Security posture collector (Windows only).

- Antivirus: WMI ``root\\SecurityCenter2`` AntiVirusProduct
- Firewall: ``netsh advfirewall show allprofiles state``
- BitLocker: ``manage-bde -status`` (best-effort, needs elevation for detail)
- Pending updates: Microsoft.Update.Session COM (best-effort)

Every check degrades to ``{"available": False, "reason": ...}`` instead of
raising. All subprocess calls are bounded by timeouts.
"""

import re
import subprocess
import sys

import config


def _wmi(namespace):
    if sys.platform != "win32":
        return None
    try:
        import wmi  # noqa: PLC0415

        return wmi.WMI(namespace=namespace)
    except Exception:
        return None


def _run(cmd, timeout=None):
    timeout = config.SUBPROCESS_TIMEOUT if timeout is None else timeout
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return proc.stdout or ""
    except Exception:
        return ""


def _antivirus():
    w = _wmi(r"root\SecurityCenter2")
    if w is None:
        return {"available": False, "reason": "SecurityCenter2 WMI unavailable"}
    products = []
    try:
        for av in w.AntiVirusProduct():
            state = getattr(av, "productState", 0) or 0
            # productState bits: 0x1000 == enabled, 0x100000 == up-to-date
            products.append(
                {
                    "name": getattr(av, "displayName", "Unknown"),
                    "enabled": bool(state & 0x1000),
                    "up_to_date": bool(state & 0x100000),
                    "raw_state": hex(state),
                }
            )
    except Exception as exc:
        return {"available": False, "reason": f"AV query failed: {exc}"}
    return {"available": True, "products": products}


def _firewall():
    if sys.platform != "win32":
        return {"available": False, "reason": "netsh is Windows-only"}
    out = _run(["netsh", "advfirewall", "show", "allprofiles", "state"])
    if not out.strip():
        return {"available": False, "reason": "netsh returned no output"}
    profiles = {}
    current = None
    for line in out.splitlines():
        line = line.strip()
        m = re.match(r"^(Domain|Private|Public) Profile Settings", line, re.I)
        if m:
            current = m.group(1).lower()
            profiles[current] = {}
        elif current and line.lower().startswith("state"):
            parts = line.split(None, 1)
            profiles[current]["state"] = parts[1].strip() if len(parts) > 1 else None
    if not profiles:
        return {"available": False, "reason": "could not parse netsh output"}
    return {"available": True, "profiles": profiles}


def _bitlocker():
    if sys.platform != "win32":
        return {"available": False, "reason": "manage-bde is Windows-only"}
    out = _run(["manage-bde", "-status"])
    if not out.strip():
        return {"available": False, "reason": "manage-bde returned no output"}
    volumes = []
    current = None
    for line in out.splitlines():
        m = re.match(r"Volume\s+([A-Z]:)", line)
        if m:
            current = {"volume": m.group(1)}
            volumes.append(current)
        elif current:
            m2 = re.match(r"\s*(Protection Status|Conversion Status|Encryption Method)\s*:\s*(.+)", line)
            if m2:
                current[m2.group(1).lower().replace(" ", "_")] = m2.group(2).strip()
    if not volumes:
        return {"available": False, "reason": "no BitLocker volumes reported"}
    return {"available": True, "volumes": volumes}


def _pending_updates():
    if sys.platform != "win32":
        return {"available": False, "reason": "Windows Update COM is Windows-only"}
    try:
        import win32com.client  # noqa: PLC0415

        session = win32com.client.Dispatch("Microsoft.Update.Session")
        searcher = session.CreateUpdateSearcher()
        # Search for not-installed software updates; can be slow, keep tight.
        result = searcher.Search("IsInstalled=0 and Type='Software'")
        updates = []
        for i in range(min(result.Updates.Count, config.MAX_UPDATES_LISTED)):
            u = result.Updates.Item(i)
            updates.append({"title": u.Title, "kb": ", ".join(
                f"KB{kb}" for kb in getattr(u, "KBArticleIDs", [])
            ) or None})
        return {"available": True, "count": result.Updates.Count, "updates": updates}
    except Exception as exc:
        return {"available": False, "reason": f"update search failed: {exc}"}


def collect():
    return {
        "available": True,
        "antivirus": _antivirus(),
        "firewall": _firewall(),
        "bitlocker": _bitlocker(),
        "pending_updates": _pending_updates(),
    }
