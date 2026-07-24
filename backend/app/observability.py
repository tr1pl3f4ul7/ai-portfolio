"""Sentry error tracking, initialised with privacy as the default.

Sentry captures exceptions *and the context around them*, and this backend
handles data that must not leave the VM: a `/contact` body is a real person's
name, email and message; a `/chat` body is a visitor's question. So the
integration is configured to send the error, the stack trace and the code —
and deliberately **not** the request body, headers, cookies, or client IP.

Off unless a DSN is set, which means off locally and off in tests. Turning it
on is a VM-only act.
"""

from __future__ import annotations

from app.config import (
    SENTRY_DSN,
    SENTRY_ENVIRONMENT,
    SENTRY_TRACES_SAMPLE_RATE,
)

# Header names that must never reach Sentry. Lower-cased for comparison. The
# Authorization header would carry nothing useful here, but scrubbing it is
# free insurance against a future change that adds one.
_SENSITIVE_HEADERS = {"authorization", "cookie", "x-real-ip", "x-forwarded-for"}


def scrub_event(event: dict, _hint: dict) -> dict:
    """`before_send` hook: strip anything that could carry personal data.

    `send_default_pii=False` already tells Sentry not to attach bodies, IPs or
    cookies. This is the belt to that braces: it runs on every event and removes
    the same things by hand, so a future SDK default flipping back on cannot
    silently start leaking. Defence in depth for exactly the data this project
    took care to keep off the wire everywhere else.
    """
    request = event.get("request")
    if isinstance(request, dict):
        # The request body is the crown jewels here — a name, email and message,
        # or a visitor's question. It never goes out.
        request.pop("data", None)
        request.pop("cookies", None)
        # Query strings can carry anything a client chose to put there.
        request.pop("query_string", None)

        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                name: value
                for name, value in headers.items()
                if name.lower() not in _SENSITIVE_HEADERS
            }

    # Client IP, if the SDK attached one despite send_default_pii=False.
    user = event.get("user")
    if isinstance(user, dict):
        user.pop("ip_address", None)

    return event


def init_sentry() -> bool:
    """Initialise Sentry if a DSN is configured. Returns whether it was enabled.

    Imported lazily so the SDK is only loaded when actually used, and so that a
    machine without a DSN — every dev machine, every test run — never pays for
    importing it.
    """
    if not SENTRY_DSN:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # The master switch for personal data. Off means no request bodies, no
        # headers, no cookies, no client IP attached to events by default.
        send_default_pii=False,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        # The hand-scrub above, on top of the flag.
        before_send=scrub_event,
        before_send_transaction=scrub_event,
    )
    return True
