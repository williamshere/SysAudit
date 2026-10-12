"""SysAudit configuration: the small set of tunables for the audit run."""

# Report title shown in the HTML header.
REPORT_TITLE = "SysAudit Report"

# Subprocess timeout (seconds) for netsh / manage-bde queries.
SUBPROCESS_TIMEOUT = 15

# Cap on individual Windows Update titles listed in the report.
MAX_UPDATES_LISTED = 50
