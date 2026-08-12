"""
Route target for ZKTeco device traffic.

Place at: apps/iaes_custom/iaes_custom/www/iclock.py

The website_route_rules entry in hooks.py maps /iclock/<anything> here,
which then hands off to the real handler in api/biometric.py.

Keeping this file thin means all the protocol logic lives in one place
and stays unit-testable.
"""

import frappe
from iaes_custom.api.biometric import iclock as _handler

# Allow unauthenticated access — the device cannot log in.
# Auth is by serial-number whitelist inside the handler.
no_cache = 1


def get_context(context):
    return _handler()
