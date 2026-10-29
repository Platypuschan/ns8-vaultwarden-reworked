"""One-time tickets for the Vaultwarden admin page.

NS8 authorizes open-admin for the user who runs it, from that user's
browser. A ticket proves this once to Vaultwarden, which exchanges it for
a short admin session: no NS8 credential reaches the application.
"""
import hashlib
import json
import os
import secrets
import time

# Mounted at /ns8-admin-tickets in the container. Only ticket hashes are
# stored: Vaultwarden renames a file to use it, so a ticket works once.
TICKET_DIR = 'admin-tickets'
TICKET_SECONDS = 60
# A session ends this long after its last renewal. The module page renews
# it every quarter of this time while it is open, so losing the right to
# run open-admin ends the admin access within this time.
SESSION_SECONDS = 120


def issue_ticket(user, directory=None, now=None):
    if not user:
        raise ValueError('open-admin requires an NS8 user')
    directory = directory or TICKET_DIR
    now = time.time() if now is None else now
    os.makedirs(directory, mode=0o700, exist_ok=True)
    purge(directory, now)
    ticket = secrets.token_urlsafe(32)
    path = os.path.join(directory, hashlib.sha256(ticket.encode()).hexdigest())
    # Write under a different name, then publish it complete
    temporary = path + '.new'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'user': user, 'expires': int(now) + TICKET_SECONDS}, stream)
    os.replace(temporary, path)
    return ticket


def purge(directory, now):
    """Remove tickets nobody used, and leftovers of interrupted writes."""
    for name in os.listdir(directory):
        path = os.path.join(directory, name)
        try:
            if os.stat(path).st_mtime < now - 2 * TICKET_SECONDS:
                os.unlink(path)
        except FileNotFoundError:
            pass
