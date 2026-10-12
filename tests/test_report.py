"""Report tests: HTML structure/escaping and JSON round-trip, using a
synthetic inventory (no real machine data, no Windows APIs)."""

import json
import os

from report import generate_html, generate_json, write_reports


def _inventory():
    return {
        "hardware": {
            "available": True,
            "cpu": {
                "model": "Test CPU 9000",
                "physical_cores": 8,
                "logical_cores": 16,
                "max_clock_mhz": 5200,
            },
            "ram": {"total": "32.0 GB", "slots_used": 2, "speed_mts": [5600]},
            "disks": [
                {"model": "TEST NVMe 1TB", "size": "931.5 GB", "interface": "NVMe"}
            ],
            "gpus": [
                {"name": "Test GPU", "vram": "12.0 GB", "driver_version": "1.0"}
            ],
            "motherboard": {"manufacturer": "TestBoard", "model": "TB-1"},
            "bios": {"manufacturer": "TestBIOS", "version": "1.0", "release_date": "20240101"},
            "system_serial_number": "TEST123",
            "monitors": [
                {"manufacturer": "TST", "product": "P27", "serial": "SN1"}
            ],
        },
        "os": {
            "available": True,
            "hostname": 'Evil<script>alert("x")</script>PC',
            "edition": "Test Windows 11 Pro",
            "build_number": "22631",
            "architecture": "64-bit",
            "domain": None,
            "workgroup": "WORKGROUP",
            "install_date": "2024-01-01 10:00",
            "last_boot": "2026-10-12 08:00",
            "windows_activated": True,
        },
        "software": {
            "available": True,
            "count": 2,
            "programs": [
                {"name": "App One", "version": "1.0", "publisher": "Acme"},
                {"name": "App Two", "version": None, "publisher": None},
            ],
        },
        "network": {
            "available": True,
            "adapters": [
                {
                    "name": "Ethernet",
                    "is_up": True,
                    "mac": "AA-BB-CC-DD-EE-FF",
                    "ipv4": [{"address": "192.168.1.10", "netmask": "255.255.255.0"}],
                    "dhcp_enabled": True,
                    "gateway": ["192.168.1.1"],
                    "dns_servers": ["192.168.1.1"],
                }
            ],
        },
        "security": {
            "available": True,
            "antivirus": {
                "available": True,
                "products": [
                    {"name": "Test AV", "enabled": True, "up_to_date": True}
                ],
            },
            "firewall": {
                "available": True,
                "profiles": {"domain": {"state": "ON"}, "private": {"state": "ON"}},
            },
            "bitlocker": {
                "available": True,
                "volumes": [
                    {
                        "volume": "C:",
                        "protection_status": "Protection On",
                        "conversion_status": "Fully Encrypted",
                    }
                ],
            },
            "pending_updates": {"available": False, "reason": "no backend in test"},
        },
    }


def test_html_contains_all_sections():
    page = generate_html(_inventory(), generated_at="2026-10-12 09:00")
    for section in (
        "Hardware",
        "Operating System",
        "Installed Software",
        "Network",
        "Security",
    ):
        assert section in page
    assert "Test CPU 9000" in page
    assert "App One" in page
    assert "192.168.1.10" in page
    assert "Test AV" in page


def test_html_escapes_hostile_values():
    page = generate_html(_inventory())
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


def test_html_marks_unavailable_collectors():
    inv = _inventory()
    inv["software"] = {"available": False, "reason": "nope"}
    page = generate_html(inv)
    assert "nope" in page


def test_json_round_trips():
    inv = _inventory()
    assert json.loads(generate_json(inv)) == inv


def test_write_reports_both(tmp_path):
    written = write_reports(_inventory(), str(tmp_path), fmt="both")
    assert len(written) == 2
    assert written[0].endswith(".html") and os.path.exists(written[0])
    assert written[1].endswith(".json") and os.path.exists(written[1])


def test_write_reports_format_choices(tmp_path):
    assert len(write_reports(_inventory(), str(tmp_path), fmt="html")) == 1
    assert len(write_reports(_inventory(), str(tmp_path), fmt="json")) == 1
