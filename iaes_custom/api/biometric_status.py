"""
Biometric Device Status Dashboard — data layer
==============================================

Read-only status endpoint for biometric device monitoring.
No device control, no configuration changes — reporting only.

Place at: iaes_custom/api/biometric_status.py

Called by: iaes_custom/www/biometric_status.html (+ .py controller)
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, get_datetime, time_diff_in_seconds, cint


# A device is considered offline if it has not pushed within this window.
# Generous enough to survive a quiet afternoon without crying wolf.
STALE_AFTER_HOURS = 12


@frappe.whitelist()
def get_status():
    """
    Full status payload. Requires an authenticated session —
    do not change to allow_guest.
    """
    return {
        "devices":        _device_status(),
        "configured":     _configured_serials(),
        "today":          _today_summary(),
        "unmapped":       _unmapped_device_users(),
        "employees":      _employee_mapping(),
        "recent_punches": _recent_punches(),
        "settings":       _settings(),
        "server_time":    str(now_datetime()),
    }


def _configured_serials():
    allowed = frappe.conf.get("biometric_allowed_serials") or []
    if isinstance(allowed, str):
        allowed = [s.strip() for s in allowed.split(",") if s.strip()]
    return allowed


def _settings():
    return {
        "infer_log_type":   bool(frappe.conf.get("biometric_infer_log_type")),
        "stale_after_hours": STALE_AFTER_HOURS,
    }


def _device_status():
    """
    Every device that has ever pushed a punch, plus whitelisted serials
    that have never been seen (so a silent new device is visible, not absent).
    """
    rows = frappe.db.sql("""
        SELECT
            IFNULL(device_id, '(blank)') AS device_id,
            COUNT(*)   AS total_punches,
            MAX(time)  AS last_punch,
            MIN(time)  AS first_punch,
            SUM(CASE WHEN DATE(time) = CURDATE() THEN 1 ELSE 0 END) AS punches_today
        FROM `tabEmployee Checkin`
        GROUP BY device_id
        ORDER BY last_punch DESC
    """, as_dict=True)

    now = now_datetime()
    seen_ids = set()

    for r in rows:
        seen_ids.add(r.device_id)
        if r.last_punch:
            secs = time_diff_in_seconds(now, get_datetime(r.last_punch))
            r["hours_since"] = round(secs / 3600.0, 1)
            r["online"]      = secs < (STALE_AFTER_HOURS * 3600)
            r["ago"]         = _humanise(secs)
        else:
            r["hours_since"] = None
            r["online"]      = False
            r["ago"]         = "never"
        r["whitelisted"] = r.device_id in _configured_serials()
        r["last_punch"]  = str(r.last_punch) if r.last_punch else None
        r["first_punch"] = str(r.first_punch) if r.first_punch else None

    # Whitelisted but never seen
    for serial in _configured_serials():
        if serial not in seen_ids:
            rows.append({
                "device_id": serial, "total_punches": 0, "punches_today": 0,
                "last_punch": None, "first_punch": None, "hours_since": None,
                "online": False, "ago": "never", "whitelisted": True,
            })

    return rows


def _today_summary():
    row = frappe.db.sql("""
        SELECT
            COUNT(*) AS punches,
            COUNT(DISTINCT employee) AS employees,
            SUM(CASE WHEN log_type = 'IN'  THEN 1 ELSE 0 END) AS ins,
            SUM(CASE WHEN log_type = 'OUT' THEN 1 ELSE 0 END) AS outs
        FROM `tabEmployee Checkin`
        WHERE DATE(time) = CURDATE()
    """, as_dict=True)
    d = row[0] if row else {}

    # Still on site = has an IN today but no later OUT
    on_site = frappe.db.sql("""
        SELECT COUNT(*) AS n FROM (
            SELECT employee,
                   MAX(CASE WHEN log_type='IN'  THEN time END) AS last_in,
                   MAX(CASE WHEN log_type='OUT' THEN time END) AS last_out
            FROM `tabEmployee Checkin`
            WHERE DATE(time) = CURDATE()
            GROUP BY employee
        ) t
        WHERE t.last_in IS NOT NULL
          AND (t.last_out IS NULL OR t.last_out < t.last_in)
    """, as_dict=True)

    d["on_site"] = on_site[0]["n"] if on_site else 0
    return d


def _unmapped_device_users(limit=25):
    """
    Device user IDs that pushed punches but match no Employee.
    Sourced from the error log the ingest handler writes.
    """
    logs = frappe.get_all(
        "Error Log",
        filters={"error": ["like", "%Unmapped device user%"]},
        fields=["name", "creation", "error"],
        order_by="creation desc",
        limit=cint(limit) * 4,
    )

    seen, out = set(), []
    for lg in logs:
        uid = _extract_user_id(lg.error)
        if uid and uid not in seen:
            seen.add(uid)
            out.append({
                "user_id":  uid,
                "last_seen": str(lg.creation),
                "log":      lg.name,
            })
        if len(out) >= cint(limit):
            break
    return out


def _extract_user_id(text):
    import re
    m = re.search(r"user_id '([^']+)'", text or "")
    if m:
        return m.group(1)
    m = re.search(r"Unmapped device user (\S+)", text or "")
    return m.group(1) if m else None


def _employee_mapping():
    """Active employees with a device ID, plus duplicate detection."""
    emps = frappe.db.sql("""
        SELECT name, employee_name, attendance_device_id, branch, department
        FROM `tabEmployee`
        WHERE status = 'Active'
          AND IFNULL(attendance_device_id, '') != ''
        ORDER BY
            CASE WHEN attendance_device_id REGEXP '^[0-9]+$'
                 THEN CAST(attendance_device_id AS UNSIGNED) ELSE 999999 END,
            employee_name
    """, as_dict=True)

    by_id = {}
    for e in emps:
        by_id.setdefault(e.attendance_device_id, []).append(e.employee_name)
    duplicates = [
        {"device_id": k, "employees": v}
        for k, v in by_id.items() if len(v) > 1
    ]

    unmapped_count = frappe.db.count(
        "Employee", {"status": "Active", "attendance_device_id": ["in", ["", None]]}
    )

    nums = sorted(int(e.attendance_device_id) for e in emps
                  if str(e.attendance_device_id).isdigit())

    return {
        "mapped":          emps,
        "mapped_count":    len(emps),
        "unmapped_count":  unmapped_count,
        "duplicates":      duplicates,
        "numeric_min":     min(nums) if nums else None,
        "numeric_max":     max(nums) if nums else None,
        "next_free":       (max(nums) + 1) if nums else 1,
    }


def _recent_punches(limit=20):
    rows = frappe.db.sql("""
        SELECT ec.employee, ec.employee_name, ec.time, ec.log_type,
               IFNULL(ec.device_id, '-') AS device_id, e.branch
        FROM `tabEmployee Checkin` ec
        LEFT JOIN `tabEmployee` e ON e.name = ec.employee
        ORDER BY ec.time DESC
        LIMIT %(limit)s
    """, {"limit": cint(limit)}, as_dict=True)
    for r in rows:
        r["time"] = str(r["time"])
    return rows


def _humanise(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return "%d min ago" % (seconds // 60)
    if seconds < 86400:
        h = seconds // 3600
        return "%d hour%s ago" % (h, "" if h == 1 else "s")
    d = seconds // 86400
    return "%d day%s ago" % (d, "" if d == 1 else "s")
