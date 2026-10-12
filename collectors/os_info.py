"""Operating-system inventory collector.

Sources: stdlib ``platform`` (cross-platform) plus WMI Win32_OperatingSystem /
Win32_ComputerSystem and the SoftwareLicensingProduct class on Windows
(guarded, best-effort).
"""

import datetime
import platform
import sys


def _wmi():
    if sys.platform != "win32":
        return None
    try:
        import wmi  # noqa: PLC0415

        return wmi.WMI()
    except Exception:
        return None


def _wmi_datetime(value):
    """Convert a WMI datetime string (yyyymmddHHMMSS...) to ISO date."""
    try:
        text = str(value)
        dt = datetime.datetime.strptime(text[:14], "%Y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def collect():
    data = {"available": True}

    data["hostname"] = platform.node() or None
    data["platform"] = platform.system()
    data["os_release"] = platform.release()
    data["os_version"] = platform.version()

    w = _wmi()
    if w is not None:
        try:
            oses = w.Win32_OperatingSystem()
            if oses:
                osys = oses[0]
                data["edition"] = (osys.Caption or "").strip() or None
                data["build_number"] = osys.BuildNumber
                data["architecture"] = osys.OSArchitecture
                data["install_date"] = _wmi_datetime(osys.InstallDate)
                data["last_boot"] = _wmi_datetime(osys.LastBootUpTime)
        except Exception:
            pass
        try:
            systems = w.Win32_ComputerSystem()
            if systems:
                cs = systems[0]
                if cs.PartOfDomain:
                    data["domain"] = cs.Domain
                    data["workgroup"] = None
                else:
                    data["domain"] = None
                    data["workgroup"] = cs.Workgroup or cs.Domain
        except Exception:
            pass
        # Activation status: LicenseStatus 1 == Licensed
        try:
            licensed = False
            for product in w.SoftwareLicensingProduct():
                app_id = str(getattr(product, "ApplicationId", "")).lower()
                if app_id == "55c92734-d682-4d71-983e-d6ec3f16059f" and getattr(
                    product, "PartialProductKey", None
                ):
                    licensed = int(getattr(product, "LicenseStatus", 0) or 0) == 1
                    break
            data["windows_activated"] = licensed
        except Exception:
            data["windows_activated"] = None
    else:
        # Non-Windows fallback: uptime from boot time when psutil exists
        data["edition"] = None
        try:
            import psutil  # noqa: PLC0415

            boot = datetime.datetime.fromtimestamp(psutil.boot_time())
            data["last_boot"] = boot.strftime("%Y-%m-%d %H:%M")
        except Exception:
            data["last_boot"] = None

    return data
