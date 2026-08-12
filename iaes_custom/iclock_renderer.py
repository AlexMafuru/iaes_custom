"""
Page renderer for ZKTeco ADMS device traffic.

Frappe's www/ pages expect an HTML template, which does not suit a device
protocol that needs raw plain-text responses. A page renderer intercepts
the path before template resolution and returns a Response directly.

Registered in hooks.py:
    page_renderer = ["iaes_custom.iclock_renderer.IClockRenderer"]
"""

from werkzeug.wrappers import Response


class IClockRenderer:
    def __init__(self, path, http_status_code=None):
        self.path = path
        self.http_status_code = http_status_code

    def can_render(self):
        return (self.path or "").lstrip("/").startswith("iclock")

    def render(self):
        from iaes_custom.api.biometric import iclock
        body = iclock() or "OK"
        return Response(
            body,
            status=200,
            mimetype="text/plain",
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )
