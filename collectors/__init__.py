"""SysAudit collectors.

Each collector module exposes a single ``collect()`` function that returns a
plain dict of findings. Collectors must NEVER raise on missing backends:
when a data source is unavailable they return
``{"available": False, "reason": "..."}`` instead.
"""

from . import hardware, network, os_info, security, software

__all__ = ["hardware", "network", "os_info", "security", "software"]


def run_all():
    """Run every collector, isolating failures so one bad collector
    never kills the whole audit."""
    results = {}
    for name, module in (
        ("hardware", hardware),
        ("os", os_info),
        ("software", software),
        ("network", network),
        ("security", security),
    ):
        try:
            results[name] = module.collect()
        except Exception as exc:  # noqa: BLE001 - audit must not crash
            results[name] = {"available": False, "reason": f"collector error: {exc}"}
    return results
