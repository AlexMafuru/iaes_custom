"""
ZKTeco ADMS (Push SDK) Integration for IAES Custom
===================================================

Implements the actual ZKTeco "iclock" push protocol used by MB360, MB560,
K40 Pro, MB1000 and similar terminals. The device initiates all contact —
ERPNext never connects out to the device.

PROTOCOL OVERVIEW
-----------------
The device makes four kinds of request. Each must be answered correctly or
the device marks the server unreachable and stops pushing.

1. HANDSHAKE   GET  /iclock/cdata?SN=<sn>&options=all&pushver=2.4.1
               -> plain-text config block (see _handshake_response)

2. ATTENDANCE  POST /iclock/cdata?SN=<sn>&table=ATTLOG&Stamp=<stamp>
               body: tab-delimited rows, one punch per line
               -> "OK: <count>"

3. COMMAND     GET  /iclock/getrequest?SN=<sn>
               -> "OK"  (no pending commands)

4. CMD RESULT  POST /iclock/devicecmd?SN=<sn>
               -> "OK"

ATTLOG ROW FORMAT (tab-separated)
---------------------------------
    user_id  timestamp            status  verify  workcode  reserved
    101      2026-08-11 08:15:32  0       1       0         0

  status: 0=Check In, 1=Check Out, 2=Break Out, 3=Break In,
          4=OT In, 5=OT Out   (depends on firmware / F-key config)
  verify: 1=fingerprint, 15=face, 2=password, 3=card

AUTHENTICATION
--------------
By device serial number. Only serials listed in site config
`biometric_allowed_serials` are accepted. The serial is printed on the
device sticker and shown in Menu > System Info.

    "biometric_allowed_serials": ["ABC1234567890"]

This is the protocol's own auth model — ZKTeco firmware has no field for
custom HTTP headers or bearer tokens. The endpoint therefore does nothing
except create Employee Checkin rows for known serials and known user IDs.

EMPLOYEE MAPPING
----------------
Device user_id must equal the Employee's `attendance_device_id` field.
"""

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime, cint
from datetime import timedelta


# ── Configuration ────────────────────────────────────────────────────────────
DEDUP_WINDOW_SECONDS = 60

# ZKTeco status code -> ERPNext log_type.
# Some firmware reports 0 for every punch when the F1..F4 state keys are not
# pressed. In that case set "biometric_infer_log_type": true in site config
# and the handler alternates IN/OUT from the employee's previous punch.
STATUS_MAP = {
    0: "IN",
    1: "OUT",
    2: "OUT",   # Break Out
    3: "IN",    # Break In
    4: "IN",    # OT In
    5: "OUT",   # OT Out
}


# ═════════════════════════════════════════════════════════════════════════════
# Route entry point
# ═════════════════════════════════════════════════════════════════════════════

@frappe.whitelist(allow_guest=True)
def iclock(**kwargs):
    """
    Single entry point for all /iclock/* device traffic.

    Wired up via website_route_rules in hooks.py:
        {"from_route": "/iclock/<path:iclock_path>", "to_route": "iclock"}

    Always returns plain text — ZKTeco firmware cannot parse JSON and will
    treat a JSON body as a failed push.
    """
    try:
        path   = frappe.form_dict.get("iclock_path", "") or ""
        serial = (frappe.form_dict.get("SN") or "").strip()
        method = frappe.request.method

        if not _is_allowed_serial(serial):
            _log("Rejected serial",
                 f"Unknown device serial '{serial}' called {path}")
            # Reply OK so an unknown/rogue device stops hammering the server
            return _text("OK")

        if path.startswith("cdata"):
            if method == "GET":
                return _text(_handshake_response(serial))
            return _text(_handle_cdata_post(serial))

        if path.startswith("getrequest"):
            return _text("OK")

        if path.startswith("devicecmd"):
            return _text("OK")

        return _text("OK")

    except Exception:
        frappe.log_error(
            title="ZKTeco iclock handler crashed",
            message=frappe.get_traceback(),
        )
        # Always reply OK — an HTTP 500 makes some firmware discard its
        # buffer, losing punches permanently.
        return _text("OK")


# ═════════════════════════════════════════════════════════════════════════════
# Handshake
# ═════════════════════════════════════════════════════════════════════════════

def _handshake_response(serial):
    """
    Plain-text config block returned on the device's first contact.

        Delay          seconds between getrequest polls
        TransInterval  minutes between batch uploads
        TransFlag      which tables to push (attlog, oplog, attphoto, ...)
        TimeZone       hours offset from UTC — 3 for Tanzania (EAT)
        Realtime       1 = push each punch immediately
    """
    return "\n".join([
        f"GET OPTION FROM: {serial}",
        "ATTLOGStamp=None",
        "OPERLOGStamp=9999",
        "ATTPHOTOStamp=None",
        "ErrorDelay=30",
        "Delay=10",
        "TransTimes=00:00;14:00",
        "TransInterval=1",
        "TransFlag=1111000000",
        "TimeZone=3",
        "Realtime=1",
        "Encrypt=0",
    ])


# ═════════════════════════════════════════════════════════════════════════════
# Attendance ingest
# ═════════════════════════════════════════════════════════════════════════════

def _handle_cdata_post(serial):
    """Parse an ATTLOG batch and create Employee Checkin rows."""
    table = (frappe.form_dict.get("table") or "").upper()

    if table and table != "ATTLOG":
        # OPERLOG (admin/door events), ATTPHOTO, etc — acknowledge only
        return "OK"

    raw   = frappe.request.get_data(as_text=True) or ""
    lines = [ln for ln in raw.splitlines() if ln.strip()]

    created = skipped = 0
    for line in lines:
        try:
            if _process_attlog_line(line, serial):
                created += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1
            frappe.log_error(
                title="ZKTeco ATTLOG row failed",
                message=f"Serial: {serial}\nRow: {line}\n\n{frappe.get_traceback()}",
            )

    if created:
        frappe.db.commit()

    # ZKTeco expects "OK: <number of records accepted>"
    return f"OK: {created + skipped}"


def _process_attlog_line(line, serial):
    """
    Parse one tab-delimited ATTLOG row and create a checkin.
    Returns True if a record was created, False if skipped.
    """
    parts = [p.strip() for p in line.split("\t")]
    if len(parts) < 2:
        return False

    user_id   = parts[0]
    timestamp = parts[1]
    status    = cint(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    if not user_id or not timestamp:
        return False

    try:
        punch_dt = get_datetime(timestamp)
    except Exception:
        return False

    employee = frappe.db.get_value(
        "Employee",
        {"attendance_device_id": user_id, "status": "Active"},
        "name",
    )
    if not employee:
        _log(
            f"Unmapped device user {user_id}",
            f"Device {serial} sent a punch for user_id '{user_id}' at "
            f"{timestamp}, but no active Employee has "
            f"attendance_device_id = {user_id}.",
        )
        return False

    log_type = _resolve_log_type(employee, punch_dt, status)

    if _is_duplicate(employee, punch_dt, log_type):
        return False

    doc = frappe.new_doc("Employee Checkin")
    doc.employee  = employee
    doc.time      = punch_dt
    doc.log_type  = log_type
    doc.device_id = serial
    doc.insert(ignore_permissions=True)
    return True


def _resolve_log_type(employee, punch_dt, status):
    """Map the device status code to IN/OUT, or infer it if configured."""
    if frappe.conf.get("biometric_infer_log_type"):
        last = frappe.db.sql(
            """
            SELECT log_type FROM `tabEmployee Checkin`
            WHERE employee = %(emp)s
              AND DATE(time) = %(day)s
              AND time <= %(ts)s
            ORDER BY time DESC LIMIT 1
            """,
            {"emp": employee, "day": punch_dt.date(), "ts": punch_dt},
            as_dict=True,
        )
        if last and last[0]["log_type"] == "IN":
            return "OUT"
        return "IN"

    return STATUS_MAP.get(status, "IN")


def _is_duplicate(employee, punch_dt, log_type):
    """
    True if a matching punch already exists within the dedup window.
    Guards against the device re-pushing a batch it believes failed.
    """
    lower = punch_dt - timedelta(seconds=DEDUP_WINDOW_SECONDS)
    upper = punch_dt + timedelta(seconds=DEDUP_WINDOW_SECONDS)
    return bool(frappe.db.sql(
        """
        SELECT name FROM `tabEmployee Checkin`
        WHERE employee = %(emp)s AND log_type = %(log)s
          AND time BETWEEN %(lo)s AND %(up)s
        LIMIT 1
        """,
        {"emp": employee, "log": log_type, "lo": lower, "up": upper},
    ))


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _is_allowed_serial(serial):
    allowed = frappe.conf.get("biometric_allowed_serials") or []
    if isinstance(allowed, str):
        allowed = [s.strip() for s in allowed.split(",")]
    return bool(serial) and serial in allowed


def _text(body):
    """Return plain text — ZKTeco firmware cannot parse JSON responses."""
    frappe.local.response["type"] = "page"
    frappe.local.response["page_name"] = None
    frappe.local.response_headers = {"Content-Type": "text/plain; charset=utf-8"}
    frappe.local.response["http_status_code"] = 200
    frappe.local.response["message"] = body
    return body


def _log(title, message):
    frappe.log_error(title=f"Biometric: {title}", message=message)


# ═════════════════════════════════════════════════════════════════════════════
# Diagnostics (authenticated — open in a logged-in browser tab)
# ═════════════════════════════════════════════════════════════════════════════

@frappe.whitelist()
def health_check():
    """
    /api/method/iaes_custom.api.biometric.health_check
    """
    allowed = frappe.conf.get("biometric_allowed_serials") or []
    if isinstance(allowed, str):
        allowed = [s.strip() for s in allowed.split(",")]

    devices = frappe.db.sql(
        """
        SELECT device_id, COUNT(*) AS punches, MAX(time) AS last_punch
        FROM `tabEmployee Checkin`
        WHERE device_id IS NOT NULL AND device_id != ''
        GROUP BY device_id
        ORDER BY last_punch DESC
        """,
        as_dict=True,
    )

    return {
        "serials_configured": allowed,
        "serials_count":      len(allowed),
        "infer_log_type":     bool(frappe.conf.get("biometric_infer_log_type")),
        "mapped_employees":   frappe.db.count(
            "Employee", {"attendance_device_id": ["!=", ""], "status": "Active"}
        ),
        "devices_seen":       devices,
        "server_time":        str(now_datetime()),
    }


@frappe.whitelist()
def recent_errors(limit=20):
    """
    /api/method/iaes_custom.api.biometric.recent_errors
    Last N biometric-related error log entries, newest first.
    """
    return frappe.get_all(
        "Error Log",
        filters={"error": ["like", "%Biometric%"]},
        fields=["creation", "error"],
        order_by="creation desc",
        limit=cint(limit),
    )
