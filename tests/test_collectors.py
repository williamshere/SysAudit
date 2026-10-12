"""Collector tests: run on Linux with mocks; never touch real Windows APIs."""

import sys
from unittest import mock

import pytest

from collectors import hardware, network, os_info, run_all, security, software


def test_run_all_never_raises_when_a_collector_explodes():
    with mock.patch.object(
        hardware, "collect", side_effect=RuntimeError("boom")
    ):
        results = run_all()
    assert results["hardware"]["available"] is False
    assert "boom" in results["hardware"]["reason"]
    # every other collector still ran
    assert set(results) == {"hardware", "os", "software", "network", "security"}


def test_run_all_returns_all_sections():
    results = run_all()
    assert set(results) == {"hardware", "os", "software", "network", "security"}


def test_hardware_collect_degrades_without_wmi():
    with mock.patch.object(hardware, "_wmi", return_value=None), mock.patch.object(
        hardware, "_reg_cpu_name", return_value=None
    ):
        data = hardware.collect()
    assert data["available"] is True
    assert "model" in data["cpu"]
    assert data["motherboard"]["available"] is False
    assert data["bios"]["available"] is False
    assert data["monitors"] == []


def test_hardware_collect_uses_psutil_on_linux():
    data = hardware.collect()
    assert data["cpu"]["logical_cores"] and data["cpu"]["logical_cores"] > 0
    assert data["ram"].get("total_bytes", 0) > 0


def test_software_unavailable_off_windows():
    data = software.collect()
    if sys.platform != "win32":
        assert data["available"] is False
        assert "registry" in data["reason"].lower()
    else:
        assert data["available"] is True
        assert isinstance(data["programs"], list)


def test_software_read_uninstall_key_parses_values():
    if sys.platform != "win32":
        pytest.skip("registry parsing is Windows-only")
    import winreg

    fake_values = {
        "DisplayName": ("My App", None),
        "DisplayVersion": ("1.2.3", None),
        "Publisher": ("Acme", None),
    }

    class FakeKey:
        pass

    with mock.patch.object(winreg, "OpenKey") as m_open, mock.patch.object(
        winreg, "QueryInfoKey", return_value=(1,)
    ), mock.patch.object(winreg, "EnumKey", return_value="sub"), mock.patch.object(
        winreg, "CloseKey"
    ), mock.patch.object(
        winreg,
        "QueryValueEx",
        side_effect=lambda sk, name: fake_values.get(name, (None, None))
        if name in fake_values
        else (_ for _ in ()).throw(OSError()),
    ):
        m_open.return_value = FakeKey()
        rows = software._read_uninstall_key(winreg.HKEY_LOCAL_MACHINE, "x")
    assert rows == [{"name": "My App", "version": "1.2.3", "publisher": "Acme"}]


def test_network_collect_returns_adapter_list():
    data = network.collect()
    assert data["available"] is True
    assert isinstance(data["adapters"], list)
    for adapter in data["adapters"]:
        assert "name" in adapter


def test_security_subchecks_degrade_off_windows():
    data = security.collect()
    assert data["available"] is True
    if sys.platform != "win32":
        for key in ("antivirus", "firewall", "bitlocker", "pending_updates"):
            assert data[key]["available"] is False, key


def test_os_info_collect_has_hostname():
    data = os_info.collect()
    assert data["available"] is True
    assert data["hostname"]  # non-empty on any platform
    assert isinstance(data["platform"], str) and data["platform"]
