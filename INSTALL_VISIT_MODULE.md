# Installing the Visit Management module into iaes_custom

## 0. Before extracting

Commit your current work first, so the change is a clean diff:

```bash
cd ~/frappe-bench/apps/iaes_custom
git status          # save/commit anything pending (you had 1 unsaved file in VS Code)
git add -A && git commit -m "checkpoint before visit module"
```

## 1. Extract

Extract this zip so its `iaes_custom/` folder merges into the repo root
`~/frappe-bench/apps/iaes_custom/`. From WSL:

```bash
unzip -o iaes_custom_visit_module.zip -d ~/frappe-bench/apps/
```

Files REPLACED (both were reproduced with your existing content intact):
- `iaes_custom/hooks.py`     - doctype_js extended; scheduler_events,
  override_doctype_dashboards, after_install/after_migrate added at the bottom
- `iaes_custom/modules.txt`  - "Visit Management" added as a second line

Files ADDED (all new, nothing else touched):
- `iaes_custom/visit_management/`            - the whole module
- `iaes_custom/public/js/customer_visit_button.js`
- `iaes_custom/public/js/lead_visit_button.js`

`patches.txt` is NOT changed. Setup runs from an idempotent
`after_migrate` hook instead of a patch, because Frappe skips patches on
fresh installs (they are marked completed without running) - the hook
covers migrate and fresh-install alike.

## 2. Verify the diff, then migrate (bench start running in another terminal)

```bash
cd ~/frappe-bench/apps/iaes_custom
git diff hooks.py modules.txt     # review - should match the list above
cd ~/frappe-bench
bench --site visit.local migrate
bench build --app iaes_custom
```

Restart bench start (Ctrl+C, then `bench start`) so the scheduler picks up
the new cron entries.

## 3. Local test checklist (visit.local)

1. Desk > search "Visit Management" - workspace opens with 4 number cards.
2. Visit Management Settings - set Sales Manager = your user.
3. Create a Sales Person linked to an Employee with a user_id.
4. Create a Visit Target for that Sales Person (2/week).
5. New Customer Visit - party type Customer - pick a customer - Save.
   Check: assignment ToDo created, contact details fetched.
6. New Customer Visit with party type Lead - confirm it works without a customer.
7. Open a visit - Close Visit button - fill the dialog with
   Follow-up Required + type "Site Visit" - confirm a new linked
   Customer Visit appears.
8. Set one visit's date to yesterday, leave it Open - list view should
   show it red "Overdue".
9. Run all five reports under the workspace.
10. Customer form - check the "Visits" section appears in the
    connections area, and Create > Visit works.

## 4. Deploy to production

```bash
cd ~/frappe-bench/apps/iaes_custom
git add -A
git commit -m "Add Visit Management module: customer visit planning, execution and reports"
git push
```

Then in Frappe Cloud: your bench group picks up the push (auto or
"Deploy" button, per your current flow) - after deploy, the site
migrates, the after_migrate hook creates the cards, and the module is
live. No per-site install step is needed since iaes_custom is already
installed on the production site.

## 5. First-run configuration on production

- Visit Management Settings: set Sales Manager (Alex), confirm digests on.
- Create the 4 Sales Person records if missing; each needs
  Employee -> user_id for assignment emails.
- One Visit Target per sales person.
- Frappe Cloud runs the scheduler automatically; the three cron jobs
  appear under "Scheduled Job Type" after migrate.
