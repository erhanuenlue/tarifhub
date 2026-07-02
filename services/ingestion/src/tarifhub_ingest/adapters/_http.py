"""Redirect-refusing HTTP opener shared by the source-fetch adapters.

The adapters validate scheme + host on the URL they are *handed* (SSRF guard). But
``urllib``'s default opener silently follows 30x redirects to ANY host, so a hostile
or compromised endpoint could 302 a pinned-host request off to an internal address —
the validation would only ever have covered the initial URL. BAG static files have no
business redirecting, so we fail closed: any 30x response raises ``ValueError`` naming
the rejected ``Location``. This is the only network seam and it is never used by tests.
"""

from __future__ import annotations

import urllib.request
from typing import Any


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """An ``HTTPRedirectHandler`` that refuses every redirect instead of following it.

    Raising here (rather than returning ``None``) gives a clear, host-naming error and
    guarantees the pinned-host check can never be bypassed by a 30x to another host.
    """

    def redirect_request(  # noqa: PLR0913 — urllib's fixed redirect-hook signature
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        """Refuse the redirect with a host-naming error (urllib override hook)."""

        raise ValueError(
            f"fetch refused a {code} redirect to {newurl!r}; the scheme/host pin only "
            "covers the initial URL, so redirects are not followed (fail closed)"
        )


_OPENER = urllib.request.build_opener(_RefuseRedirects())


def open_no_redirect(request: urllib.request.Request, *, timeout: float) -> Any:
    """Open ``request`` with the shared redirect-refusing opener.

    Any 30x response raises ``ValueError`` (via :class:`_RefuseRedirects`) before a
    single byte is read from an unpinned host. Returns the same context-manager
    response object as :func:`urllib.request.urlopen`.
    """

    return _OPENER.open(request, timeout=timeout)
