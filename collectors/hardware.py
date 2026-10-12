"""Hardware inventory collector.

Sources (best-effort, guarded):
- psutil: CPU counts/freq, RAM total, disk partitions/usage (cross-platform)
- WMI (Windows only): CPU model, RAM slots/speed, physical disks, GPUs,
  motherboard, BIOS, serial number, monitors
"""

import platform
import sys

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def _wmi(namespace=r"root\cimv2"):
    """Return a WMI connection or None when unavailable (non-Windows,
    missing pywin32/wmi package, or COM failure)."""
    if sys.platform != "win32":
        return None
    try:
        import wmi  # noqa: PLC0415

        return wmi.WMI(namespace=namespace)
    except Exception:
        return None


def _reg_cpu_name():
    """CPU model from the registry (works without admin rights)."""
    if sys.platform != "win32":
        return None
    try:
        import winreg  # noqa: PLC0415

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        )
        name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
        winreg.CloseKey(key)
        return name.strip() if name else None
    except Exception:
        return None


def _decode_wmi_monitor_id(blob):
    """Decode a WmiMonitorID byte array into a readable string."""
    if not blob:
        return None
    try:
        chars = [c for c in bytes(blob) if c != 0]
        text = bytes(chars).decode("utf-16-le", errors="ignore").strip()
        return text or None
    except Exception:
        return None


def _fmt_bytes(num):
    if num is None:
        return None
    step = 1024.0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < step:
            return f"{num:.1f} {unit}"
        num /= step
    return f"{num:.1f} PB"


def collect():
    data = {"available": True}

    # ---- CPU ----
    cpu = {}
    if psutil is not None:
        try:
            cpu["physical_cores"] = psutil.cpu_count(logical=False)
            cpu["logical_cores"] = psutil.cpu_count(logical=True)
            freq = psutil.cpu_freq()
            if freq:
                cpu["max_clock_mhz"] = round(freq.max or freq.current or 0, 0) or None
        except Exception:
            pass
    model = _reg_cpu_name()
    if not model:
        w = _wmi()
        if w is not None:
            try:
                procs = w.Win32_Processor()
                if procs:
                    model = procs[0].Name.strip()
                    cpu.setdefault("max_clock_mhz", procs[0].MaxClockSpeed)
            except Exception:
                pass
    cpu["model"] = model or platform.processor() or "Unknown"
    data["cpu"] = cpu

    # ---- RAM ----
    ram = {}
    if psutil is not None:
        try:
            ram["total"] = _fmt_bytes(psutil.virtual_memory().total)
            ram["total_bytes"] = psutil.virtual_memory().total
        except Exception:
            pass
    w = _wmi()
    if w is not None:
        try:
            sticks = w.Win32_PhysicalMemory()
            if sticks:
                ram["slots_used"] = len(sticks)
                speeds = {int(s.Speed) for s in sticks if getattr(s, "Speed", None)}
                if speeds:
                    ram["speed_mts"] = sorted(speeds)
        except Exception:
            pass
    data["ram"] = ram

    # ---- Disks ----
    disks = []
    if w is not None:
        try:
            for d in w.Win32_DiskDrive():
                disks.append(
                    {
                        "model": (d.Model or "Unknown").strip(),
                        "size": _fmt_bytes(int(d.Size)) if d.Size else None,
                        "interface": d.InterfaceType,
                    }
                )
        except Exception:
            pass
    if not disks and psutil is not None:
        try:
            seen = set()
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                except Exception:
                    continue
                key = part.device
                if key in seen:
                    continue
                seen.add(key)
                disks.append(
                    {
                        "model": None,
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "filesystem": part.fstype,
                        "size": _fmt_bytes(usage.total),
                    }
                )
        except Exception:
            pass
    data["disks"] = disks or {"available": False, "reason": "no disk data"}

    # ---- GPU / motherboard / BIOS / serial / monitors (WMI only) ----
    gpus = []
    board = {}
    bios = {}
    serial = None
    monitors = []
    if w is not None:
        try:
            for g in w.Win32_VideoController():
                gpus.append(
                    {
                        "name": (g.Name or "Unknown").strip(),
                        "vram": _fmt_bytes(int(g.AdapterRAM))
                        if g.AdapterRAM and int(g.AdapterRAM) > 0
                        else None,
                        "driver_version": g.DriverVersion,
                    }
                )
        except Exception:
            pass
        try:
            boards = w.Win32_BaseBoard()
            if boards:
                b = boards[0]
                board = {
                    "manufacturer": (b.Manufacturer or "").strip() or None,
                    "model": (b.Product or "").strip() or None,
                }
        except Exception:
            pass
        try:
            bioses = w.Win32_BIOS()
            if bioses:
                b = bioses[0]
                bios = {
                    "manufacturer": (b.Manufacturer or "").strip() or None,
                    "version": (b.SMBIOSBIOSVersion or "").strip() or None,
                    "release_date": str(b.ReleaseDate or "")[:8] or None,
                }
                serial = (b.SerialNumber or "").strip() or None
        except Exception:
            pass
        try:
            wm = _wmi(namespace=r"root\wmi")
            if wm is not None:
                for m in wm.WmiMonitorID():
                    monitors.append(
                        {
                            "manufacturer": _decode_wmi_monitor_id(
                                getattr(m, "ManufacturerName", None)
                            ),
                            "product": _decode_wmi_monitor_id(
                                getattr(m, "ProductCodeID", None)
                            ),
                            "serial": _decode_wmi_monitor_id(
                                getattr(m, "SerialNumberID", None)
                            ),
                        }
                    )
        except Exception:
            pass

    data["gpus"] = gpus
    data["motherboard"] = board or {"available": False, "reason": "WMI unavailable"}
    data["bios"] = bios or {"available": False, "reason": "WMI unavailable"}
    data["system_serial_number"] = serial
    data["monitors"] = monitors

    return data
