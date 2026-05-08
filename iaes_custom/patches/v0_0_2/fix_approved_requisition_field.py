"""
One-time migration: fix the misspelled custom field on Material Request.

Background:
    At some point a custom field was created on Material Request named
    `custom_approved_requisition_no` of type Int (default 0). It was then
    deleted and recreated as Data — but with a typo, leaving us with two
    columns:

        custom_approved_requisition_no   INT(11)       — orphan ghost, default 0
        custom_approved_requistion_no    VARCHAR(140)  — actual data, with typo

    Application code (NMB HQ Monthly Billing report, generate_quotation.py)
    queries the correctly-spelled name and silently gets 0 for every row
    while the real requisition numbers sit in the misspelled column.

This patch:
    1. Snapshots data from the misspelled column.
    2. Drops the orphan INT column (no real data, just default 0s plus
       one stale test value).
    3. Renames the misspelled VARCHAR column to the correct spelling.
    4. Updates the Custom Field metadata to match.
    5. Restores data into the renamed column (defensive — rename SHOULD
       preserve it but we're being safe).
    6. Verifies row count.

Idempotent — safe to re-run. After the first successful run, all checks
short-circuit and the patch is a no-op.
"""

import frappe


def execute():
    """Entry point called by `bench migrate`."""
    print("=" * 70)
    print("NMB Patch: fix Material Request 'custom_approved_requisition_no'")
    print("=" * 70)

    # Inspect current schema state
    columns = _get_custom_columns("tabMaterial Request")
    has_typo = "custom_approved_requistion_no" in columns
    has_correct = "custom_approved_requisition_no" in columns
    correct_type = columns.get("custom_approved_requisition_no", {}).get("type", "")

    print(f"  Has typo column      (custom_approved_requistion_no):   {has_typo}")
    print(f"  Has correct-named col (custom_approved_requisition_no): {has_correct}  ({correct_type})")

    # Idempotency check — if only the correctly-named VARCHAR exists, we're done
    if has_correct and not has_typo and "varchar" in correct_type.lower():
        print("  → Schema already correct. Nothing to do.")
        return

    if not has_typo and not has_correct:
        print("  → Neither column found. Was the field never created on this site? Skipping.")
        return

    # Step 1 — Snapshot data from the typo column
    snapshot = []
    if has_typo:
        snapshot = frappe.db.sql(
            """
            SELECT name, custom_approved_requistion_no AS req_no
            FROM `tabMaterial Request`
            WHERE custom_approved_requistion_no IS NOT NULL
              AND custom_approved_requistion_no != ''
            """,
            as_dict=True,
        )
        print(f"  Step 1: snapshotted {len(snapshot)} rows of data from typo column.")

    # Step 2 — Drop the orphan INT column if present
    if has_correct and "int" in correct_type.lower():
        frappe.db.sql(
            "ALTER TABLE `tabMaterial Request` DROP COLUMN `custom_approved_requisition_no`"
        )
        print("  Step 2: dropped orphan INT column.")
    elif has_correct:
        print(f"  Step 2: skipped — correctly-named column is already type {correct_type}.")

    # Step 3 — Rename the typo column
    if has_typo:
        frappe.db.sql(
            """
            ALTER TABLE `tabMaterial Request`
            CHANGE COLUMN `custom_approved_requistion_no`
                          `custom_approved_requisition_no`
                          VARCHAR(140) DEFAULT NULL
            """
        )
        print("  Step 3: renamed typo column to correct spelling.")

    # Step 4 — Update the Custom Field metadata
    typo_record = frappe.db.exists(
        "Custom Field", {"dt": "Material Request", "fieldname": "custom_approved_requistion_no"}
    )
    correct_record = frappe.db.exists(
        "Custom Field", {"dt": "Material Request", "fieldname": "custom_approved_requisition_no"}
    )

    if typo_record and not correct_record:
        frappe.db.sql(
            """
            UPDATE `tabCustom Field`
            SET fieldname = 'custom_approved_requisition_no',
                name      = 'Material Request-custom_approved_requisition_no'
            WHERE name = 'Material Request-custom_approved_requistion_no'
            """
        )
        print("  Step 4: updated Custom Field metadata.")
    elif correct_record and typo_record:
        # Edge case: both metadata records exist. Keep the correct one, delete the typo.
        frappe.delete_doc("Custom Field", "Material Request-custom_approved_requistion_no", force=1)
        print("  Step 4: deleted duplicate typo Custom Field record.")
    else:
        print("  Step 4: Custom Field record already correct.")

    # Step 5 — Defensive data restore (in case rename dropped it)
    restored = 0
    if snapshot:
        for r in snapshot:
            current = frappe.db.get_value(
                "Material Request", r["name"], "custom_approved_requisition_no"
            )
            if not current and r["req_no"]:
                frappe.db.set_value(
                    "Material Request",
                    r["name"],
                    "custom_approved_requisition_no",
                    r["req_no"],
                    update_modified=False,
                )
                restored += 1
        if restored:
            print(f"  Step 5: restored {restored} rows where rename lost data.")
        else:
            print("  Step 5: rename preserved all data, no restore needed.")

    frappe.db.commit()

    # Final verification
    final_columns = _get_custom_columns("tabMaterial Request")
    final_has_typo = "custom_approved_requistion_no" in final_columns
    final_has_correct = "custom_approved_requisition_no" in final_columns
    final_type = final_columns.get("custom_approved_requisition_no", {}).get("type", "")

    final_count = frappe.db.sql(
        """
        SELECT COUNT(*) AS n
        FROM `tabMaterial Request`
        WHERE custom_approved_requisition_no IS NOT NULL
          AND custom_approved_requisition_no != ''
        """,
        as_dict=True,
    )[0]["n"]

    print("=" * 70)
    print("Final state:")
    print(f"  custom_approved_requistion_no  (typo)   exists: {final_has_typo}      (expected False)")
    print(f"  custom_approved_requisition_no (correct) exists: {final_has_correct}  ({final_type})")
    print(f"  Rows with data: {final_count}  (expected ~{len(snapshot) if snapshot else 'N/A'})")
    print("=" * 70)

    if final_has_typo or not final_has_correct or "varchar" not in final_type.lower():
        frappe.throw("Patch verification failed — manual cleanup needed.")

    # Clear cache so doctype meta reflects new fieldname
    frappe.clear_cache(doctype="Material Request")
    print("Cache cleared.")


def _get_custom_columns(table_name):
    """Returns dict of {column_name: {'type': column_type}} for custom_* columns."""
    rows = frappe.db.sql(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME LIKE 'custom_%%'
        """,
        (table_name,),
        as_dict=True,
    )
    return {r["COLUMN_NAME"]: {"type": r["COLUMN_TYPE"]} for r in rows}
