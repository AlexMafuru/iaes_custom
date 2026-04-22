import frappe
from frappe import _
from frappe.utils import date_diff, flt, cint, getdate, get_first_day, get_last_day, nowdate, now_datetime
from datetime import datetime, date, timedelta, time as dtime

# ── Shift configuration ─────────────────────────────────────────────────────
SHIFT_IN_TIME      = dtime(7, 30, 0)
SHIFT_OUT_TIME     = dtime(17, 0,  0)
SHIFT_OUT_SAT      = dtime(13, 0,  0)
STANDARD_HOURS     = 9.5
STANDARD_HOURS_SAT = 5.5
LATE_GRACE_MINS    = 10
EARLY_EXIT_MINS    = 15


def get_columns(filters):
    mode = (filters or {}).get("report_mode", "Summary")
    base = [
        {"fieldname": "employee",      "label": _("Employee ID"),   "fieldtype": "Link", "options": "Employee", "width": 110},
        {"fieldname": "employee_name", "label": _("Employee Name"), "fieldtype": "Data", "width": 175},
    ]
    if mode == "Daily Detail":
        base += [
            {"fieldname": "attendance_date", "label": _("Date"),         "fieldtype": "Date",  "width": 100},
            {"fieldname": "day_name",        "label": _("Day"),           "fieldtype": "Data",  "width": 70},
            {"fieldname": "first_in",        "label": _("First IN"),      "fieldtype": "Data",  "width": 85},
            {"fieldname": "last_out",        "label": _("Last OUT"),      "fieldtype": "Data",  "width": 85},
            {"fieldname": "work_hours",      "label": _("Work Hrs"),      "fieldtype": "Float", "width": 85,  "precision": 2},
            {"fieldname": "overtime_hours",  "label": _("OT Hrs"),        "fieldtype": "Float", "width": 75,  "precision": 2},
            {"fieldname": "late_entry",      "label": _("Late In"),       "fieldtype": "Data",  "width": 80},
            {"fieldname": "early_exit",      "label": _("Early Out"),     "fieldtype": "Data",  "width": 85},
            {"fieldname": "missing_punch",   "label": _("Missing Punch"), "fieldtype": "Data",  "width": 105},
            {"fieldname": "day_status",      "label": _("Status"),        "fieldtype": "Data",  "width": 120},
        ]
    else:
        base += [
            {"fieldname": "total_working_days", "label": _("Working Days"),    "fieldtype": "Int",     "width": 110},
            {"fieldname": "checked_in",          "label": _("Checked In"),      "fieldtype": "Int",     "width": 95},
            {"fieldname": "checked_out",         "label": _("Checked Out"),     "fieldtype": "Int",     "width": 100},
            {"fieldname": "on_site",             "label": _("On Site"),         "fieldtype": "Int",     "width": 80},
            {"fieldname": "present_days",        "label": _("Present"),         "fieldtype": "Float",   "width": 80},
            {"fieldname": "absent_days",         "label": _("Absent"),          "fieldtype": "Float",   "width": 80},
            {"fieldname": "late_entries",        "label": _("Late In"),         "fieldtype": "Int",     "width": 75},
            {"fieldname": "early_exits",         "label": _("Early Out"),       "fieldtype": "Int",     "width": 85},
            {"fieldname": "missing_punches",     "label": _("Missing Punch"),   "fieldtype": "Int",     "width": 110},
            {"fieldname": "holiday_ot_days",     "label": _("Holiday OT Days"), "fieldtype": "Int",     "width": 110},
            {"fieldname": "total_work_hours",    "label": _("Total Hrs"),       "fieldtype": "Float",   "width": 90,  "precision": 1},
            {"fieldname": "overtime_hours",      "label": _("OT Hrs"),          "fieldtype": "Float",   "width": 80,  "precision": 1},
            {"fieldname": "avg_work_hours",      "label": _("Avg Hrs/Day"),     "fieldtype": "Float",   "width": 100, "precision": 2},
            {"fieldname": "attendance_pct",      "label": _("Attendance %"),    "fieldtype": "Percent", "width": 115},
            {"fieldname": "status_summary",      "label": _("Status"),          "fieldtype": "Data",    "width": 125},
        ]
    return base


def execute(filters=None):
    if not filters:
        filters = {}
    _validate_filters(filters)
    columns      = get_columns(filters)
    mode         = filters.get("report_mode", "Summary")
    employees    = _get_employees(filters)
    emp_ids      = [e["name"] for e in employees]
    checkins     = _get_checkins(emp_ids, filters["from_date"], filters["to_date"])
    holidays     = _get_holiday_set(employees, filters["from_date"], filters["to_date"])
    working_days = _build_working_days_set(filters["from_date"], filters["to_date"], holidays)
    daily_map    = _build_daily_map(checkins, holidays, filters["to_date"])
    if mode == "Daily Detail":
        data = _build_detail_rows(employees, daily_map, working_days, holidays)
    else:
        data = _build_summary_rows(employees, daily_map, working_days, holidays, filters["to_date"])
    chart   = _get_chart(data, mode)
    summary = _get_summary_cards(data, mode, filters["to_date"])
    return columns, data, None, chart, summary


def _validate_filters(filters):
    if not filters.get("from_date") or not filters.get("to_date"):
        frappe.throw(_("Both From Date and To Date are required."))
    if getdate(filters["from_date"]) > getdate(filters["to_date"]):
        frappe.throw(_("From Date cannot be after To Date."))
    if date_diff(filters["to_date"], filters["from_date"]) > 365:
        frappe.throw(_("Date range cannot exceed 366 days."))


def _get_employees(filters):
    conds = {"status": "Active"}
    if filters.get("employee"):
        conds["name"] = filters["employee"]
    if filters.get("department"):
        conds["department"] = filters["department"]
    if filters.get("site") and frappe.db.has_column("Employee", "branch"):
        conds["branch"] = filters["site"]
    return frappe.get_all(
        "Employee", filters=conds,
        fields=["name", "employee_name", "department", "designation", "holiday_list", "default_shift"],
        order_by="employee_name"
    )


def _get_checkins(employee_ids, from_date, to_date):
    if not employee_ids:
        return []
    return frappe.db.sql(
        """
        SELECT ec.employee, ec.employee_name,
               DATE(ec.time) AS attendance_date,
               TIME(ec.time) AS punch_time,
               ec.log_type
        FROM `tabEmployee Checkin` ec
        WHERE ec.employee IN %(employees)s
          AND DATE(ec.time) BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY ec.employee, ec.time
        """,
        {"employees": employee_ids, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )


def _get_holiday_set(employees, from_date, to_date):
    holiday_dates = set()
    from_dt = getdate(from_date)

    def _fetch_holidays(hl_name, seen):
        if not hl_name or hl_name in seen:
            return
        seen.add(hl_name)
        rows = frappe.get_all(
            "Holiday",
            filters={"parent": hl_name, "holiday_date": ["between", [from_date, to_date]]},
            fields=["holiday_date"]
        )
        for r in rows:
            holiday_dates.add(getdate(r["holiday_date"]))

    def _find_best_holiday_list(base_hl):
        if not base_hl:
            return None
        candidates = frappe.get_all(
            "Holiday List",
            filters={"from_date": ["<=", to_date], "to_date": [">=", from_date]},
            fields=["name", "from_date", "to_date"],
            order_by="from_date desc"
        )
        if not candidates:
            return base_hl
        target_year = from_dt.year
        for c in candidates:
            if getdate(c["from_date"]).year == target_year:
                return c["name"]
        return candidates[0]["name"]

    seen = set()
    for emp in employees:
        base_hl = emp.get("holiday_list") or frappe.db.get_single_value(
            "HR Settings", "default_holiday_list"
        )
        best_hl = _find_best_holiday_list(base_hl)
        _fetch_holidays(best_hl, seen)
        if base_hl and base_hl != best_hl:
            _fetch_holidays(base_hl, seen)
    return holiday_dates


def _build_working_days_set(from_date, to_date, holidays):
    working = set()
    cur = getdate(from_date)
    end = getdate(to_date)
    while cur <= end:
        if cur.weekday() < 6 and cur not in holidays:
            working.add(cur)
        cur += timedelta(days=1)
    return working


def _build_daily_map(checkins, holidays, to_date):
    # Use frappe's now_datetime to get server local time (timezone-aware)
    today_local = getdate(nowdate())
    to_dt       = getdate(to_date)
    # "today" in report context = to_date if it equals today, otherwise no in-progress
    is_report_today = (to_dt == today_local)

    buckets = {}
    for row in checkins:
        key = (row["employee"], row["attendance_date"])
        if key not in buckets:
            buckets[key] = {"employee_name": row["employee_name"], "ins": [], "outs": []}
        t = _to_time(row["punch_time"])
        if row["log_type"] == "IN":
            buckets[key]["ins"].append(t)
        elif row["log_type"] == "OUT":
            buckets[key]["outs"].append(t)

    result = {}
    for (emp, att_date), b in buckets.items():
        ins  = sorted(b["ins"])
        outs = sorted(b["outs"])
        first_in = ins[0]   if ins  else None
        last_out = outs[-1] if outs else None

        d            = getdate(att_date)
        is_today     = is_report_today and (d == to_dt)
        is_sunday    = d.weekday() == 6
        is_saturday  = d.weekday() == 5
        is_holiday   = d in holidays
        is_full_ot_day = is_holiday or is_sunday

        shift_out = SHIFT_OUT_SAT    if is_saturday else SHIFT_OUT_TIME
        std_hrs   = STANDARD_HOURS_SAT if is_saturday else STANDARD_HOURS

        # Work hours
        work_hours = 0.0
        if first_in and last_out:
            base   = date(2000, 1, 1)
            dt_in  = datetime.combine(base, first_in)
            dt_out = datetime.combine(base, last_out)
            work_hours = max((dt_out - dt_in).total_seconds() / 3600, 0)
        elif first_in and is_today and not last_out:
            # Still working — hours so far using server local time
            now_t  = now_datetime().time()
            base   = date(2000, 1, 1)
            dt_in  = datetime.combine(base, first_in)
            dt_now = datetime.combine(base, now_t)
            work_hours = max((dt_now - dt_in).total_seconds() / 3600, 0)

        # Overtime
        if is_full_ot_day:
            overtime_h = work_hours
        else:
            overtime_h = max(work_hours - std_hrs, 0) if work_hours else 0.0

        # Late entry
        late_entry = False
        late_by_mins = 0
        if first_in and not is_full_ot_day:
            threshold_in = datetime.combine(date.today(), SHIFT_IN_TIME) + timedelta(minutes=LATE_GRACE_MINS)
            actual_in    = datetime.combine(date.today(), first_in)
            if actual_in > threshold_in:
                late_entry   = True
                late_by_mins = int((actual_in - datetime.combine(date.today(), SHIFT_IN_TIME)).total_seconds() / 60)

        # Early exit
        early_exit = False
        early_by_mins = 0
        if last_out and not is_full_ot_day:
            threshold_out = datetime.combine(date.today(), shift_out) - timedelta(minutes=EARLY_EXIT_MINS)
            actual_out    = datetime.combine(date.today(), last_out)
            if actual_out < threshold_out:
                early_exit    = True
                early_by_mins = int((datetime.combine(date.today(), shift_out) - actual_out).total_seconds() / 60)

        # Missing punch
        missing_punch = (not ins) or (not outs)
        if is_full_ot_day:
            missing_punch = False
            missing_type  = ""
        elif not ins and outs:
            missing_type = "Missing IN"
        elif ins and not outs:
            if is_today:
                missing_punch = False
                missing_type  = "In Progress"
            else:
                missing_type = "Missing OUT"
        elif not ins and not outs:
            missing_type = "No punches"
        else:
            missing_type = ""

        result[(emp, att_date)] = {
            "employee_name":  b["employee_name"],
            "first_in":       _fmt_time(first_in),
            "last_out":       _fmt_time(last_out) if last_out else ("Active" if is_today else "-"),
            "work_hours":     flt(work_hours, 2),
            "overtime_hours": flt(overtime_h, 2),
            "late_entry":     late_entry,
            "late_by_mins":   late_by_mins,
            "early_exit":     early_exit,
            "early_by_mins":  early_by_mins,
            "missing_punch":  missing_punch,
            "missing_type":   missing_type,
            "is_holiday":     is_holiday,
            "is_sunday":      is_sunday,
            "is_saturday":    is_saturday,
            "is_full_ot_day": is_full_ot_day,
            "is_today":       is_today,
            "has_in":         bool(ins),
            "has_out":        bool(outs),
        }
    return result


def _build_detail_rows(employees, daily_map, working_days, holidays):
    rows = []
    for emp in employees:
        emp_id = emp["name"]
        all_days = set(working_days)
        for (e, d), punch in daily_map.items():
            if e == emp_id and punch.get("is_full_ot_day"):
                all_days.add(getdate(d))

        for day in sorted(all_days):
            punch      = daily_map.get((emp_id, day))
            is_holiday = day in holidays
            is_saturday = day.weekday() == 5
            is_sunday   = day.weekday() == 6

            if is_sunday:       day_label = "Sun (Rest)"
            elif is_saturday:   day_label = "Sat"
            else:               day_label = day.strftime("%a")
            if is_holiday:      day_label += " (PH)"

            if punch:
                late_lbl    = f"+{punch['late_by_mins']}m"  if punch["late_entry"]    else "On time"
                early_lbl   = f"-{punch['early_by_mins']}m" if punch["early_exit"]    else "Normal"
                missing_lbl = punch["missing_type"]          if punch["missing_punch"] else "-"
                wh, oth     = punch["work_hours"], punch["overtime_hours"]

                if punch["is_full_ot_day"]:                       status = "Holiday OT"
                elif punch.get("missing_type") == "In Progress":  status = "In Progress"
                elif punch["missing_punch"]:                       status = "Incomplete"
                elif punch["late_entry"] and punch["early_exit"]: status = "Late + Early"
                elif punch["late_entry"]:                          status = "Late"
                elif punch["early_exit"]:                          status = "Early Exit"
                elif oth > 0:                                      status = "Overtime"
                else:                                              status = "Present"
            else:
                late_lbl = early_lbl = missing_lbl = "-"
                wh = oth = 0.0
                status = "Absent" if day in working_days else "-"

            if status == "-":
                continue

            rows.append({
                "employee":       emp_id,
                "employee_name":  emp["employee_name"],
                "attendance_date":str(day),
                "day_name":       day_label,
                "first_in":       punch["first_in"]  if punch else "-",
                "last_out":       punch["last_out"]  if punch else "-",
                "work_hours":     wh,
                "overtime_hours": oth,
                "late_entry":     late_lbl,
                "early_exit":     early_lbl,
                "missing_punch":  missing_lbl,
                "day_status":     status,
            })
    return rows


def _build_summary_rows(employees, daily_map, working_days, holidays, to_date):
    rows = []
    total_wd   = len(working_days)
    today_date = getdate(to_date)

    for emp in employees:
        emp_id = emp["name"]
        present = late_count = early_count = missing_count = holiday_ot_days = 0
        checked_in_today = checked_out_today = on_site_now = 0
        total_wh = ot_total = 0.0
        present_for_avg = 0

        for day in working_days:
            punch = daily_map.get((emp_id, day))
            if punch:
                in_progress = punch.get("missing_type") == "In Progress"

                if not punch["missing_punch"] or in_progress:
                    present += 1
                    present_for_avg += 1
                    total_wh += punch["work_hours"]
                    ot_total += punch["overtime_hours"]
                else:
                    missing_count += 1

                if punch["late_entry"]:  late_count  += 1
                if punch["early_exit"]: early_count += 1

                # Today's checkin/checkout counts
                if punch.get("is_today"):
                    if punch["has_in"]:
                        checked_in_today = 1
                    if punch["has_out"]:
                        checked_out_today = 1
                    if punch["has_in"] and not punch["has_out"]:
                        on_site_now = 1

        for (e, d), punch in daily_map.items():
            if e != emp_id:
                continue
            day = getdate(d)
            if punch.get("is_full_ot_day") and punch["work_hours"] > 0:
                holiday_ot_days += 1
                ot_total        += punch["overtime_hours"]
                total_wh        += punch["work_hours"]

        absent  = max(total_wd - present - missing_count, 0)
        avg_wh  = flt(total_wh / (present_for_avg or 1), 2)
        att_pct = flt(present / total_wd * 100, 1) if total_wd else 0.0

        if att_pct >= 95:   status = "Excellent"
        elif att_pct >= 85: status = "Good"
        elif att_pct >= 75: status = "Moderate"
        else:               status = "Needs Attention"

        rows.append({
            "employee":           emp_id,
            "employee_name":      emp["employee_name"],
            "total_working_days": total_wd,
            "checked_in":         checked_in_today,
            "checked_out":        checked_out_today,
            "on_site":            on_site_now,
            "present_days":       present,
            "absent_days":        absent,
            "late_entries":       late_count,
            "early_exits":        early_count,
            "missing_punches":    missing_count,
            "holiday_ot_days":    holiday_ot_days,
            "total_work_hours":   flt(total_wh, 1),
            "overtime_hours":     flt(ot_total, 1),
            "avg_work_hours":     avg_wh,
            "attendance_pct":     att_pct,
            "status_summary":     status,
        })
    rows.sort(key=lambda x: x["attendance_pct"])
    return rows


def _get_chart(data, mode):
    if not data:
        return None
    if mode == "Daily Detail":
        by_emp    = {}
        all_dates = sorted({r["attendance_date"] for r in data})
        for r in data:
            by_emp.setdefault(r["employee_name"], {})
            by_emp[r["employee_name"]][r["attendance_date"]] = flt(r.get("work_hours", 0))
        datasets = [
            {"name": name, "values": [hrs.get(d, 0) for d in all_dates], "chartType": "bar"}
            for name, hrs in by_emp.items()
        ]
        return {"data": {"labels": all_dates, "datasets": datasets},
                "type": "bar", "height": 280, "title": "Daily Work Hours by Employee"}
    labels = [r["employee_name"] for r in data]
    return {
        "data": {"labels": labels, "datasets": [
            {"name": "Present",    "values": [r["present_days"]    for r in data], "chartType": "bar"},
            {"name": "Absent",     "values": [r["absent_days"]     for r in data], "chartType": "bar"},
            {"name": "Holiday OT", "values": [r["holiday_ot_days"] for r in data], "chartType": "bar"},
            {"name": "OT Hours",   "values": [r["overtime_hours"]  for r in data], "chartType": "line"},
        ]},
        "type": "bar", "colors": ["#2ecc71", "#e74c3c", "#9b59b6", "#3498db"],
        "height": 280, "title": "Biometric Attendance Summary",
    }


def _get_summary_cards(data, mode, to_date):
    if not data:
        return []

    is_today_report = (getdate(to_date) == getdate(nowdate()))

    if mode == "Daily Detail":
        absent     = sum(1 for r in data if r.get("day_status") == "Absent")
        late       = sum(1 for r in data if "Late" in str(r.get("day_status", "")))
        missing    = sum(1 for r in data if r.get("missing_punch", "-") not in ("-", ""))
        ot         = sum(1 for r in data if flt(r.get("overtime_hours", 0)) > 0)
        holiday_ot = sum(1 for r in data if r.get("day_status") == "Holiday OT")
        in_prog    = sum(1 for r in data if r.get("day_status") == "In Progress")
        return [
            {"value": absent,     "label": _("Absent Days"),     "indicator": "Red"    if absent     else "Green", "datatype": "Int"},
            {"value": late,       "label": _("Late Arrivals"),   "indicator": "Orange" if late       else "Green", "datatype": "Int"},
            {"value": missing,    "label": _("Missing Punches"), "indicator": "Red"    if missing    else "Green", "datatype": "Int"},
            {"value": in_prog,    "label": _("In Progress"),     "indicator": "Blue"   if in_prog    else "Green", "datatype": "Int"},
            {"value": ot,         "label": _("OT Days"),         "indicator": "Blue",                              "datatype": "Int"},
            {"value": holiday_ot, "label": _("Holiday OT Days"), "indicator": "Blue"   if holiday_ot else "Green", "datatype": "Int"},
        ]

    n             = len(data)
    avg_att       = flt(sum(r["attendance_pct"] for r in data) / n, 1) if n else 0
    total_checked_in  = sum(r.get("checked_in",  0) for r in data)
    total_checked_out = sum(r.get("checked_out", 0) for r in data)
    total_on_site     = sum(r.get("on_site",     0) for r in data)

    cards = []

    if is_today_report:
        cards += [
            {"value": total_checked_in,  "label": _("Checked In Today"),  "indicator": "Green" if total_checked_in  else "Red",    "datatype": "Int"},
            {"value": total_checked_out, "label": _("Checked Out Today"), "indicator": "Green" if total_checked_out else "Orange", "datatype": "Int"},
            {"value": total_on_site,     "label": _("Still On Site"),     "indicator": "Blue"  if total_on_site     else "Green",  "datatype": "Int"},
        ]

    cards += [
        {"value": n,       "label": _("Employees"),          "indicator": "Blue",                                  "datatype": "Int"},
        {"value": avg_att, "label": _("Avg Attendance %"),   "indicator": "Green" if avg_att >= 85 else "Orange",  "datatype": "Percent"},
        {"value": sum(r["absent_days"]     for r in data),   "label": _("Absent Days"),     "indicator": "Red"    if sum(r["absent_days"]     for r in data) else "Green", "datatype": "Float"},
        {"value": sum(r["late_entries"]    for r in data),   "label": _("Late Arrivals"),   "indicator": "Orange" if sum(r["late_entries"]    for r in data) else "Green", "datatype": "Int"},
        {"value": sum(r["missing_punches"] for r in data),   "label": _("Missing Punches"), "indicator": "Red"    if sum(r["missing_punches"] for r in data) else "Green", "datatype": "Int"},
        {"value": sum(r["holiday_ot_days"] for r in data),   "label": _("Holiday OT Days"), "indicator": "Blue"   if sum(r["holiday_ot_days"] for r in data) else "Green", "datatype": "Int"},
        {"value": flt(sum(r["overtime_hours"] for r in data), 1), "label": _("Total OT Hrs"), "indicator": "Blue", "datatype": "Float"},
        {"value": sum(1 for r in data if r["status_summary"] == "Needs Attention"),
         "label": _("Need Attention"), "indicator": "Red" if any(r["status_summary"] == "Needs Attention" for r in data) else "Green", "datatype": "Int"},
    ]
    return cards


def _to_time(t):
    if isinstance(t, dtime):
        return t
    if isinstance(t, str):
        try:
            return datetime.strptime(t, "%H:%M:%S").time()
        except ValueError:
            return dtime(0, 0, 0)
    if isinstance(t, timedelta):
        secs = int(t.total_seconds())
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return dtime(h % 24, m, s)
    return dtime(0, 0, 0)


def _fmt_time(t):
    if t is None:
        return "-"
    return _to_time(t).strftime("%H:%M")
