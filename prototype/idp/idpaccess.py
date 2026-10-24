#
# Copyright (C) 2026 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Access policy of the clients: only the current members of one LDAP
group of the user domain may sign in to a client.

The NS8 Keycloak providers implement the checks, and both succeed for
clients without a policy:

- the "ns8-client-access" required action, enabled in the realm.
  Keycloak evaluates it whenever an authentication completes: password,
  SSO cookie and federated IdP logins alike. The realm flows, and so
  the login mode and the password denial of federated accounts, are not
  changed;
- the "ns8-client-group-token-gate" protocol mapper of each restricted
  client: it refuses token issuance and refresh, for example the
  redemption of an authorization code issued before a group removal.

Both read the current memberships from LDAP: they evict the user from
the user cache before the check, so the cache of the LDAP federation
stays enabled for everything else. The policy is stored in client
attributes, and only administrators set it: a module can read the
policy of its own client, not change it.
"""

import sys
import urllib.parse

POLICY = "ns8.access_policy"
POLICY_GROUP = "group"
GROUP_ID = "ns8.access_group_id"
GROUP_PATH = "ns8.access_group_path"

ACTION = "ns8-client-access"
ACTION_NAME = "NS8 client access group"
TOKEN_GATE = "ns8-client-group-token-gate"
TOKEN_GATE_NAME = "ns8 access group"

GROUP_MAPPER_TYPE = "org.keycloak.storage.ldap.mappers.LDAPStorageMapper"
STORAGE_TYPE = "org.keycloak.storage.UserStorageProvider"

# Attributes and flows of the first prototype, migrated by reconcile()
LEGACY_GROUP_ID = "ns8.required_group_id"
LEGACY_GROUP_PATH = "ns8.required_group_path"
LEGACY_FLOW_ID = "ns8.group_gate_flow_id"
LEGACY_FLOW_PREFIX = "ns8-group-"


class PolicyError(ValueError):
    """The policy cannot be applied: the reason is in the error code."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _path(name):
    return urllib.parse.quote(name, safe="")

#
# Required action
#

def _required_action(kc, realm):
    return next((a for a in kc.get(f"/{realm}/authentication/required-actions")
        if a.get("providerId") == ACTION), None)

def action_installed(kc, realm):
    if _required_action(kc, realm):
        return True
    return any(a.get("providerId") == ACTION
        for a in kc.get(f"/{realm}/authentication/unregistered-required-actions"))

def ensure_required_action(kc, realm):
    """Register and enable the required action in the realm."""
    action = _required_action(kc, realm)
    if action is None:
        print(f"Registering required action {ACTION} in realm {realm}", file=sys.stderr)
        kc.post(f"/{realm}/authentication/register-required-action", {"providerId": ACTION, "name": ACTION_NAME})
        action = _required_action(kc, realm)
    if not action["enabled"] or action.get("defaultAction"):
        action.update({"enabled": True, "defaultAction": False})
        kc.put(f"/{realm}/authentication/required-actions/{_path(action['alias'])}", action)

def required_action_enabled(kc, realm):
    action = _required_action(kc, realm)
    return bool(action and action["enabled"])

#
# LDAP groups
#

def group_mapper(kc, realm):
    """Return (storage, mapper): the LDAP federation and its group
    mapper, if it reads the memberships from LDAP only. The federation
    may be writable, as in realms with federated IdPs. Otherwise raise
    PolicyError."""
    storages = [c for c in kc.get(f"/{realm}/components", params={"type": STORAGE_TYPE})
        if c.get("providerId") == "ldap"]
    if len(storages) != 1:
        raise PolicyError("ldap_federation_not_found")
    mappers = [m for m in kc.get(f"/{realm}/components", params={"parent": storages[0]["id"], "type": GROUP_MAPPER_TYPE})
        if m.get("providerId") == "group-ldap-mapper"
        and m.get("config", {}).get("mode") == ["READ_ONLY"]
        and m.get("config", {}).get("user.roles.retrieve.strategy") == ["LOAD_GROUPS_BY_MEMBER_ATTRIBUTE"]]
    if len(mappers) != 1:
        raise PolicyError("ldap_group_mapper_not_found")
    return storages[0], mappers[0]

def find_group(kc, realm, group):
    """Import the LDAP groups and return the representation of a group,
    by name, or raise PolicyError. Memberships are not imported: the
    checks read them from LDAP."""
    storage, mapper = group_mapper(kc, realm)
    kc.post(f"/{realm}/user-storage/{storage['id']}/mappers/{mapper['id']}/sync?direction=fedToKeycloak")
    try:
        return kc.get(f"/{realm}/group-by-path/{_path(group)}")
    except Exception:
        raise PolicyError("group_not_found") from None

#
# Policy of a client
#

def _token_gates(kc, realm, client):
    models = f"/{realm}/clients/{client['id']}/protocol-mappers/models"
    return [m for m in kc.get(models) if m.get("protocolMapper") == TOKEN_GATE]

def _ensure_token_gate(kc, realm, client):
    if not _token_gates(kc, realm, client):
        kc.post(f"/{realm}/clients/{client['id']}/protocol-mappers/models", {
            "name": TOKEN_GATE_NAME,
            "protocol": "openid-connect",
            "protocolMapper": TOKEN_GATE,
            "config": {},
        })

def restricted(client):
    return (client.get("attributes") or {}).get(POLICY) == POLICY_GROUP

def access_state(kc, realm, client):
    """Return the policy of a client. "enforced" is true only if every
    part of the policy is in place; "issues" lists the missing parts."""
    attributes = client.get("attributes") or {}
    if not restricted(client):
        return {"enforced": False, "group": None, "group_path": None, "issues": []}
    state = {"enforced": False, "group": None, "group_path": attributes.get(GROUP_PATH) or None, "issues": []}
    issues = state["issues"]
    try:
        group = kc.get(f"/{realm}/groups/{_path(attributes.get(GROUP_ID) or '-')}")
        state["group"] = group["name"]
        state["group_path"] = group["path"]
    except Exception:
        # For example the group was renamed or removed in LDAP: nobody
        # can sign in until the policy is set again
        issues.append("group_not_found")
    try:
        group_mapper(kc, realm)
    except PolicyError as ex:
        issues.append(ex.code)
    if not required_action_enabled(kc, realm):
        issues.append("required_action_disabled")
    if not _token_gates(kc, realm, client):
        issues.append("token_gate_missing")
    # The checks cover browser logins and user tokens only
    for flag in ("directAccessGrantsEnabled", "implicitFlowEnabled", "serviceAccountsEnabled"):
        if client.get(flag):
            issues.append(f"{flag}_set")
    overrides = client.get("authenticationFlowBindingOverrides") or {}
    if any(overrides.values()):
        # A private flow of the client could differ from the realm flow,
        # for example in the login mode
        issues.append("flow_override_set")
    state["enforced"] = not issues
    return state

def set_policy(kc, realm, client, group):
    """Restrict a client to the members of an LDAP group, by name. The
    client is disabled while it changes, because the changes are several
    REST calls: if one fails, the client stays disabled. Return the
    policy state."""
    if not action_installed(kc, realm):
        raise PolicyError("provider_not_installed")
    group_rep = find_group(kc, realm, group)
    was_enabled = client.get("enabled", True)
    if was_enabled:
        client["enabled"] = False
        kc.put(f"/{realm}/clients/{client['id']}", client)
    ensure_required_action(kc, realm)
    client.setdefault("attributes", {}).update({
        POLICY: POLICY_GROUP,
        GROUP_ID: group_rep["id"],
        GROUP_PATH: group_rep["path"],
    })
    client.update({"directAccessGrantsEnabled": False, "implicitFlowEnabled": False,
        "serviceAccountsEnabled": False})
    kc.put(f"/{realm}/clients/{client['id']}", client)
    _ensure_token_gate(kc, realm, client)
    client = kc.get(f"/{realm}/clients/{client['id']}")
    state = access_state(kc, realm, client)
    if not state["enforced"]:
        print(f"Access policy of client {client['clientId']} is incomplete: {state['issues']}. The client stays disabled", file=sys.stderr)
        raise PolicyError("policy_incomplete")
    if was_enabled:
        client["enabled"] = True
        kc.put(f"/{realm}/clients/{client['id']}", client)
    return state

def clear_policy(kc, realm, client):
    """Remove the access policy of a client, also a prototype policy.
    The required action stays registered: it does not restrict clients
    without a policy."""
    attributes = client.setdefault("attributes", {})
    for name in (POLICY, GROUP_ID, GROUP_PATH, LEGACY_GROUP_ID, LEGACY_GROUP_PATH, LEGACY_FLOW_ID):
        if name in attributes:
            # An empty value removes the attribute
            attributes[name] = ""
    _clear_legacy_override(kc, realm, client)
    kc.put(f"/{realm}/clients/{client['id']}", client)
    for mapper in _token_gates(kc, realm, client):
        kc.delete(f"/{realm}/clients/{client['id']}/protocol-mappers/models/{mapper['id']}")
    _remove_legacy_flows(kc, realm)

#
# Reconciliation
#

def _clear_legacy_override(kc, realm, client):
    overrides = client.get("authenticationFlowBindingOverrides") or {}
    if overrides.get("browser"):
        flows = {f["id"]: f["alias"] for f in kc.get(f"/{realm}/authentication/flows")}
        if flows.get(overrides["browser"], "").startswith(LEGACY_FLOW_PREFIX):
            overrides["browser"] = ""

def _remove_legacy_flows(kc, realm):
    """Remove the private flows of the prototype that no client binds.
    Each wrapper flow references only its own copy of the browser flow,
    and the deletion of a flow removes its subflows."""
    bound = {(c.get("authenticationFlowBindingOverrides") or {}).get("browser") for c in kc.get(f"/{realm}/clients")}
    for flow in kc.get(f"/{realm}/authentication/flows"):
        alias = flow["alias"]
        if alias.startswith(LEGACY_FLOW_PREFIX) and not alias.endswith("-login") and flow["id"] not in bound:
            print(f"Removing prototype flow {alias} of realm {realm}", file=sys.stderr)
            kc.delete(f"/{realm}/authentication/flows/{flow['id']}")
    for flow in kc.get(f"/{realm}/authentication/flows"):
        if flow["alias"].startswith(LEGACY_FLOW_PREFIX) and flow["alias"].endswith("-login") and flow["id"] not in bound:
            kc.delete(f"/{realm}/authentication/flows/{flow['id']}")

def _migrate_legacy(kc, realm, client):
    """Convert the policy of the first prototype, which bound a private
    copy of the browser flow to each client."""
    attributes = client.setdefault("attributes", {})
    print(f"Migrating the access policy of client {client['clientId']} of realm {realm}", file=sys.stderr)
    attributes.update({
        POLICY: POLICY_GROUP,
        GROUP_ID: attributes.get(LEGACY_GROUP_ID, ""),
        GROUP_PATH: attributes.get(LEGACY_GROUP_PATH, ""),
        LEGACY_GROUP_ID: "",
        LEGACY_GROUP_PATH: "",
        LEGACY_FLOW_ID: "",
    })
    _clear_legacy_override(kc, realm, client)
    kc.put(f"/{realm}/clients/{client['id']}", client)

def reconcile(kc, realm, clients):
    """Keep the access policies of a realm in place: enable the required
    action and restore the token gates of restricted clients, which only
    makes them stricter; migrate prototype policies and remove their
    flows."""
    if not action_installed(kc, realm):
        return
    for client in clients:
        if (client.get("attributes") or {}).get(LEGACY_GROUP_ID):
            _migrate_legacy(kc, realm, client)
    restricted_clients = [c for c in clients if restricted(c)]
    if restricted_clients:
        ensure_required_action(kc, realm)
    for client in restricted_clients:
        _ensure_token_gate(kc, realm, client)
    _remove_legacy_flows(kc, realm)
