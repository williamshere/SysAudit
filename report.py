"""Report generation: single-file HTML report + JSON export.

The HTML report is built with stdlib string templating and inline CSS so
v1 has zero third-party dependencies beyond psutil. Every dynamic value is
HTML-escaped.
"""

import datetime
import html
import json
import os


def _esc(value):
    if value is None:
        return '<span class="na">n/a</span>'
    return html.escape(str(value))


def _kv_row(label, value):
    return f"<tr><th>{_esc(label)}</th><td>{_esc(value)}</td></tr>"


def _section(title, body_html):
    return f"<section><h2>{_esc(title)}</h2>{body_html}</section>"


def _table(headers, rows):
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _unavailable(reason):
    return f'<p class="warn">Data unavailable: {_esc(reason)}</p>'


def _hardware_section(hw):
    if not hw.get("available", True):
        return _unavailable(hw.get("reason", "unknown"))
    parts = []
    cpu = hw.get("cpu", {})
    parts.append(
        "<h3>Processor</h3><table>"
        + _kv_row("Model", cpu.get("model"))
        + _kv_row("Physical cores", cpu.get("physical_cores"))
        + _kv_row("Logical cores", cpu.get("logical_cores"))
        + _kv_row("Max clock", f"{cpu.get('max_clock_mhz')} MHz" if cpu.get("max_clock_mhz") else None)
        + "</table>"
    )
    ram = hw.get("ram", {})
    parts.append(
        "<h3>Memory</h3><table>"
        + _kv_row("Total", ram.get("total"))
        + _kv_row("Slots used", ram.get("slots_used"))
        + _kv_row(
            "Speed",
            ", ".join(f"{s} MT/s" for s in ram.get("speed_mts", [])) or None,
        )
        + "</table>"
    )
    disks = hw.get("disks")
    if isinstance(disks, list) and disks:
        parts.append(
            "<h3>Storage</h3>"
            + _table(
                ("Model / Device", "Size", "Interface / FS"),
                [
                    (
                        d.get("model") or d.get("device"),
                        d.get("size"),
                        d.get("interface") or d.get("filesystem"),
                    )
                    for d in disks
                ],
            )
        )
    gpus = hw.get("gpus") or []
    if gpus:
        parts.append(
            "<h3>Graphics</h3>"
            + _table(
                ("Adapter", "VRAM", "Driver"),
                [(g.get("name"), g.get("vram"), g.get("driver_version")) for g in gpus],
            )
        )
    board = hw.get("motherboard", {})
    if board.get("available", True) and (board.get("manufacturer") or board.get("model")):
        parts.append(
            "<h3>Motherboard</h3><table>"
            + _kv_row("Manufacturer", board.get("manufacturer"))
            + _kv_row("Model", board.get("model"))
            + "</table>"
        )
    bios = hw.get("bios", {})
    if bios.get("available", True) and (bios.get("version") or bios.get("manufacturer")):
        parts.append(
            "<h3>BIOS</h3><table>"
            + _kv_row("Manufacturer", bios.get("manufacturer"))
            + _kv_row("Version", bios.get("version"))
            + _kv_row("Release date", bios.get("release_date"))
            + "</table>"
        )
    if hw.get("system_serial_number"):
        parts.append(
            "<h3>System</h3><table>"
            + _kv_row("Serial number", hw.get("system_serial_number"))
            + "</table>"
        )
    monitors = hw.get("monitors") or []
    if monitors:
        parts.append(
            "<h3>Monitors</h3>"
            + _table(
                ("Manufacturer", "Product", "Serial"),
                [
                    (m.get("manufacturer"), m.get("product"), m.get("serial"))
                    for m in monitors
                ],
            )
        )
    return "".join(parts)


def _os_section(osd):
    if not osd.get("available", True):
        return _unavailable(osd.get("reason", "unknown"))
    domain = osd.get("domain") or osd.get("workgroup")
    return (
        "<table>"
        + _kv_row("Hostname", osd.get("hostname"))
        + _kv_row("Edition", osd.get("edition"))
        + _kv_row("Build", osd.get("build_number"))
        + _kv_row("Architecture", osd.get("architecture"))
        + _kv_row("Domain / Workgroup", domain)
        + _kv_row("OS installed", osd.get("install_date"))
        + _kv_row("Last boot", osd.get("last_boot"))
        + _kv_row(
            "Windows activated",
            {True: "Yes", False: "No"}.get(osd.get("windows_activated"), None),
        )
        + "</table>"
    )


def _software_section(sw):
    if not sw.get("available", True):
        return _unavailable(sw.get("reason", "unknown"))
    programs = sw.get("programs", [])
    body = f"<p>{len(programs)} installed programs found.</p>"
    if programs:
        body += _table(
            ("Name", "Version", "Publisher"),
            [(p.get("name"), p.get("version"), p.get("publisher")) for p in programs],
        )
    return body


def _network_section(net):
    if not net.get("available", True):
        return _unavailable(net.get("reason", "unknown"))
    adapters = net.get("adapters")
    if not isinstance(adapters, list) or not adapters:
        return _unavailable("no adapters enumerated")
    parts = []
    for a in adapters:
        ips = [i["address"] for i in a.get("ipv4", [])]
        body = (
            "<table>"
            + _kv_row("Link", "Up" if a.get("is_up") else "Down")
            + _kv_row("MAC", a.get("mac"))
            + _kv_row("IPv4", ", ".join(ips) or None)
            + _kv_row("DHCP", {True: "Yes", False: "No"}.get(a.get("dhcp_enabled"), None))
            + _kv_row("Gateway", ", ".join(a.get("gateway", [])) or None)
            + _kv_row("DNS", ", ".join(a.get("dns_servers", [])) or None)
            + "</table>"
        )
        parts.append(f"<h3>{_esc(a.get('name', 'Unknown adapter'))}</h3>{body}")
    return "".join(parts)


def _security_section(sec):
    if not sec.get("available", True):
        return _unavailable(sec.get("reason", "unknown"))
    parts = []
    av = sec.get("antivirus", {})
    if av.get("available"):
        prods = av.get("products", [])
        if prods:
            parts.append(
                "<h3>Antivirus</h3>"
                + _table(
                    ("Product", "Enabled", "Up to date"),
                    [
                        (
                            p.get("name"),
                            "Yes" if p.get("enabled") else "No",
                            "Yes" if p.get("up_to_date") else "No",
                        )
                        for p in prods
                    ],
                )
            )
        else:
            parts.append("<h3>Antivirus</h3>" + _unavailable("no AV product registered"))
    else:
        parts.append("<h3>Antivirus</h3>" + _unavailable(av.get("reason", "unknown")))
    fw = sec.get("firewall", {})
    if fw.get("available"):
        parts.append(
            "<h3>Firewall</h3>"
            + _table(
                ("Profile", "State"),
                [(k.title(), v.get("state")) for k, v in fw.get("profiles", {}).items()],
            )
        )
    else:
        parts.append("<h3>Firewall</h3>" + _unavailable(fw.get("reason", "unknown")))
    bl = sec.get("bitlocker", {})
    if bl.get("available"):
        parts.append(
            "<h3>BitLocker</h3>"
            + _table(
                ("Volume", "Protection", "Conversion"),
                [
                    (
                        v.get("volume"),
                        v.get("protection_status"),
                        v.get("conversion_status"),
                    )
                    for v in bl.get("volumes", [])
                ],
            )
        )
    else:
        parts.append("<h3>BitLocker</h3>" + _unavailable(bl.get("reason", "unknown")))
    pu = sec.get("pending_updates", {})
    if pu.get("available"):
        body = f"<p>{pu.get('count', 0)} pending updates.</p>"
        updates = pu.get("updates", [])
        if updates:
            body += _table(
                ("Update", "KB"),
                [(u.get("title"), u.get("kb")) for u in updates],
            )
        parts.append("<h3>Windows Update</h3>" + body)
    else:
        parts.append("<h3>Windows Update</h3>" + _unavailable(pu.get("reason", "unknown")))
    return "".join(parts)


CSS = """
:root { color-scheme: light; }
body { font-family: "Segoe UI", system-ui, Arial, sans-serif; margin: 0;
       background: #f4f6f8; color: #1c2733; }
header { background: #0f2a44; color: #fff; padding: 28px 36px; }
header h1 { margin: 0 0 6px; font-size: 26px; }
header p { margin: 2px 0; color: #b9c9db; font-size: 14px; }
main { max-width: 1000px; margin: 24px auto; padding: 0 20px 40px; }
section { background: #fff; border-radius: 10px; padding: 20px 24px;
          margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
h2 { margin-top: 0; color: #0f2a44; border-bottom: 2px solid #e3eaf2;
     padding-bottom: 8px; }
h3 { color: #2c4a6b; margin-bottom: 8px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px;
        font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid #e6ebf1; }
thead th { background: #eef3f8; }
tbody tr:nth-child(even) { background: #f8fafc; }
th:first-child { width: 220px; color: #41546c; }
.warn { color: #8a5a00; background: #fff7e6; border: 1px solid #f0d48a;
        border-radius: 6px; padding: 10px 14px; }
.na { color: #8a97a5; font-style: italic; }
footer { text-align: center; color: #8a97a5; font-size: 12px; padding: 20px; }
"""


def generate_html(inventory, generated_at=None):
    """Build the full single-file HTML report from an inventory dict."""
    generated_at = generated_at or datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    hostname = (inventory.get("os") or {}).get("hostname") or "Unknown host"

    sections = [
        _section("Hardware", _hardware_section(inventory.get("hardware", {}))),
        _section("Operating System", _os_section(inventory.get("os", {}))),
        _section("Installed Software", _software_section(inventory.get("software", {}))),
        _section("Network", _network_section(inventory.get("network", {}))),
        _section("Security", _security_section(inventory.get("security", {}))),
    ]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SysAudit Report &mdash; {_esc(hostname)}</title>
<style>{CSS}</style>
</head>
<body>
<header>
<h1>SysAudit Report</h1>
<p>Host: {_esc(hostname)} &nbsp;&bull;&nbsp; Generated: {_esc(generated_at)}</p>
<p>Local-first inventory &mdash; no data left this machine.</p>
</header>
<main>
{''.join(sections)}
</main>
<footer>Generated by SysAudit</footer>
</body>
</html>
"""


def generate_json(inventory):
    """Serialize the raw inventory dict (round-trippable)."""
    return json.dumps(inventory, indent=2, default=str)


def write_reports(inventory, output_dir, fmt="both", generated_at=None):
    """Write report files; returns list of paths written."""
    os.makedirs(output_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    written = []
    if fmt in ("html", "both"):
        path = os.path.join(output_dir, f"sysaudit-report-{stamp}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(generate_html(inventory, generated_at))
        written.append(path)
    if fmt in ("json", "both"):
        path = os.path.join(output_dir, f"sysaudit-inventory-{stamp}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(generate_json(inventory))
        written.append(path)
    return written
