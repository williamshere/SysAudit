# SysAudit

SysAudit is a portable, local-first Windows system-inventory tool. Run one command and it collects a full machine audit — hardware, OS, installed software, network configuration, and security posture — then writes a professional HTML report and a JSON export you can attach to a help-desk ticket.

No installer, no network calls, no telemetry. It runs from a USB stick and nothing ever leaves the machine.

## Why this exists

This is a portfolio project built while studying IT support: it demonstrates the kind of first-response data collection a help-desk technician does on day one — *"what exactly is this machine?"* — automated into a single command.

## Requirements

- Windows 10/11 (primary target), Python 3.11+
- `pip install -r requirements.txt` (psutil; `wmi` and `pywin32` install automatically on Windows)

## Usage

```powershell
# Full audit: HTML report + JSON export in the current folder
python sysaudit.py

# HTML report only, into a specific folder
python sysaudit.py --format html --output C:\Audits

# JSON export only (for ticketing / CMDB ingestion)
python sysaudit.py --format json
```

Output files are timestamped, e.g. `sysaudit-report-20261012-133000.html`.

## What the report covers

- **Hardware** — CPU model/cores/clocks, RAM total + slots/speed, physical disks, GPUs, motherboard, BIOS version/date, system serial number, monitors
- **Operating System** — edition, build, hostname, domain/workgroup, install date, last boot, activation status
- **Installed Software** — name, version, publisher for every registered program
- **Network** — adapters with MAC, IPs, DHCP, gateway, DNS, link state
- **Security** — antivirus product/state, firewall profile states, BitLocker volume status, pending Windows Update count

Every collector degrades gracefully: if a data source needs elevation or is missing, that section reports "unavailable" instead of crashing the audit.

## Project structure

```
sysaudit.py          # CLI entry point (argparse)
config.py            # small tunables (timeouts, caps)
report.py            # HTML report (stdlib templating, inline CSS) + JSON export
collectors/
    hardware.py      # CPU/RAM/disks/GPU/board/BIOS/serial/monitors
    os_info.py       # edition/build/hostname/domain/boot/activation
    software.py      # installed programs from registry uninstall keys
    network.py       # adapters, IPs, DHCP, gateway, DNS (no external calls)
    security.py      # AV, firewall, BitLocker, pending updates
tests/               # pytest suite (report + collectors, mocked Windows APIs)
```

## Running the tests

```powershell
pip install pytest
python -m pytest
```

The suite runs on any platform: Windows-only code paths are exercised through mocks, so the tests pass on Linux/macOS too.

## Privacy note

Sample reports are never committed to this repo — real serial numbers, hostnames, and software lists stay on the audited machine.
