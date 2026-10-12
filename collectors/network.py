"""Network inventory collector.

Sources:
- psutil: interface addresses (MAC/IPv4/IPv6) and link state (cross-platform)
- WMI Win32_NetworkAdapterConfiguration (Windows only): DHCP, gateway, DNS

Deliberately no public-IP lookup and no external calls of any kind:
SysAudit is local-first.
"""

import socket
import sys

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def _wmi():
    if sys.platform != "win32":
        return None
    try:
        import wmi  # noqa: PLC0415

        return wmi.WMI()
    except Exception:
        return None


def collect():
    data = {"available": True, "adapters": []}

    wmi_configs = {}
    w = _wmi()
    if w is not None:
        try:
            for cfg in w.Win32_NetworkAdapterConfiguration(IPEnabled=True):
                wmi_configs[cfg.Description] = cfg
        except Exception:
            pass

    if psutil is None:
        data["adapters"] = {
            "available": False,
            "reason": "psutil unavailable and no WMI data",
        }
        return data

    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception as exc:
        return {"available": False, "reason": f"psutil net query failed: {exc}"}

    for name, addr_list in addrs.items():
        # Skip loopback-only interfaces; they carry no audit signal.
        non_loopback = [
            a
            for a in addr_list
            if getattr(a, "family", None) == socket.AF_INET
            and not a.address.startswith("127.")
        ]
        if not non_loopback and name.lower().startswith("lo"):
            continue
        entry = {"name": name}
        st = stats.get(name)
        entry["is_up"] = bool(st.isup) if st else None
        entry["speed_mbps"] = st.speed if st and st.speed else None
        for a in addr_list:
            fam = getattr(a, "family", None)
            if fam == socket.AF_INET:
                entry.setdefault("ipv4", []).append(
                    {"address": a.address, "netmask": a.netmask}
                )
            elif fam == socket.AF_INET6 and not a.address.startswith("fe80"):
                entry.setdefault("ipv6", []).append({"address": a.address})
            elif str(fam) == str(getattr(psutil, "AF_LINK", "AF_LINK")):
                entry["mac"] = a.address
        # Match WMI config by description or name for DHCP/gateway/DNS.
        cfg = wmi_configs.get(name)
        if cfg is None:
            for desc, c in wmi_configs.items():
                if name.lower() in desc.lower() or desc.lower() in name.lower():
                    cfg = c
                    break
        if cfg is not None:
            try:
                entry["dhcp_enabled"] = bool(cfg.DHCPEnabled)
                entry["gateway"] = list(cfg.DefaultIPGateway or [])
                entry["dns_servers"] = list(cfg.DNSServerSearchOrder or [])
            except Exception:
                pass
        data["adapters"].append(entry)

    return data
