"""Administrator-owned, per-client LDAP group policy for the prototype.

No realm-wide user filter: unrelated applications keep their own access.
An update disables the client first and never re-enables it on partial failure.
"""
import hashlib
from urllib.parse import quote

PROVIDER = "ns8-client-group-gate"
TOKEN_GATE = "ns8-client-group-token-gate"
GROUP_ID = "ns8.required_group_id"
GROUP_PATH = "ns8.required_group_path"
FLOW_ID = "ns8.group_gate_flow_id"


def q(value):
    return quote(value, safe="")


def access_state(kc, realm, client):
    attrs = client.get("attributes", {})
    group_id = attrs.get(GROUP_ID)
    flow_id = attrs.get(FLOW_ID)
    if not group_id or not flow_id:
        return {"enforced": False}
    base = "/" + q(realm)
    flows = kc.get(base + "/authentication/flows")
    flow = next((f for f in flows if f["id"] == flow_id), None)
    if flow is None:
        return {"enforced": False}
    executions = kc.get(base + "/authentication/flows/" + q(flow["alias"]) + "/executions")
    top = [e for e in executions if e.get("level", 0) == 0]
    gate = [e for e in top if e.get("providerId") == PROVIDER and e["requirement"] == "REQUIRED"]
    authentication = [e for e in top if e.get("authenticationFlow") and e["requirement"] == "REQUIRED"]
    group = kc.get(base + "/groups/" + q(group_id))
    ldap = kc.get(base + "/components", params={"type": "org.keycloak.storage.UserStorageProvider"})
    uncached = bool(ldap) and all(c.get("providerId") == "ldap"
        and c.get("config", {}).get("cachePolicy") == ["NO_CACHE"]
        and c.get("config", {}).get("editMode") == ["READ_ONLY"] for c in ldap)
    for component in ldap:
        mappers = kc.get(base + "/components", params={"parent": component["id"]})
        uncached = uncached and any(m.get("providerId") == "group-ldap-mapper"
            and m.get("config", {}).get("mode") == ["READ_ONLY"]
            and m.get("config", {}).get("user.roles.retrieve.strategy") == ["LOAD_GROUPS_BY_MEMBER_ATTRIBUTE"]
            for m in mappers)
    token_gate = any(m.get("protocolMapper") == TOKEN_GATE for m in kc.get(
        base + "/clients/" + q(client["id"]) + "/protocol-mappers/models"))
    enforced = (token_gate and len(gate) == 1 and len(authentication) == 1
        and top[-1]["id"] == gate[0]["id"]
        and client.get("authenticationFlowBindingOverrides", {}).get("browser") == flow_id
        and not client.get("directAccessGrantsEnabled", False)
        and not client.get("implicitFlowEnabled", False)
        and not client.get("serviceAccountsEnabled", False)
        and uncached)
    return {"enforced": bool(enforced), "group_path": group["path"], "group_id": group_id}


def apply(kc, realm, client_id, group_path):
    base = "/" + q(realm)
    client = kc.find_client(realm, client_id)
    if client is None:
        raise ValueError("Client must be registered before its group policy is applied")
    was_enabled = client.get("enabled", True)
    # Fail closed across REST calls (Keycloak has no transaction across requests).
    client["enabled"] = False
    kc.put(base + "/clients/" + q(client["id"]), client)
    if not group_path.startswith("/") or group_path == "/":
        raise ValueError("An exact absolute Keycloak group path is required")
    providers = kc.get(base + "/authentication/authenticator-providers")
    if not any(p["id"] == PROVIDER for p in providers):
        raise ValueError("Group gate provider is not installed")
    ldap = kc.get(base + "/components", params={"type": "org.keycloak.storage.UserStorageProvider"})
    if not ldap:
        raise ValueError("A read-only LDAP federation is required")
    for component in ldap:
        if component.get("providerId") != "ldap" or component["config"].get("editMode") != ["READ_ONLY"]:
            raise ValueError("Only read-only LDAP federation is supported")
        component["config"]["cachePolicy"] = ["NO_CACHE"]
        kc.put(base + "/components/" + q(component["id"]), component)
        mappers = kc.get(base + "/components", params={"parent": component["id"]})
        group_mappers = [m for m in mappers if m.get("providerId") == "group-ldap-mapper"
            and m.get("config", {}).get("mode") == ["READ_ONLY"]
            and m.get("config", {}).get("user.roles.retrieve.strategy") == ["LOAD_GROUPS_BY_MEMBER_ATTRIBUTE"]]
        if len(group_mappers) != 1:
            raise ValueError("Exactly one live read-only LDAP group mapper is required")
        kc.post(base + "/user-storage/" + q(component["id"]) + "/mappers/"
            + q(group_mappers[0]["id"]) + "/sync?direction=fedToKeycloak")
    group = kc.get(base + "/group-by-path/" + q(group_path.lstrip("/")))
    kc.post(base + "/clear-user-cache")

    # Re-use a complete validated flow on repeated configuration; otherwise
    # create a private copy of the current realm browser flow and wrap it.
    attrs = client.setdefault("attributes", {})
    if not attrs.get(FLOW_ID):
        realm_rep = kc.get(base)
        suffix = hashlib.sha256(client_id.encode()).hexdigest()[:16]
        wrapper_alias = "ns8-group-" + suffix
        login_alias = wrapper_alias + "-login"
        flows = kc.get(base + "/authentication/flows")
        if any(f["alias"] in (wrapper_alias, login_alias) for f in flows):
            raise ValueError("Partial policy flow exists; client remains disabled for administrator repair")
        kc.post(base + "/authentication/flows/" + q(realm_rep["browserFlow"]) + "/copy",
                {"newName": login_alias})
        kc.post(base + "/authentication/flows", {"alias": wrapper_alias,
            "providerId": "basic-flow", "topLevel": True, "builtIn": False})
        flows = kc.get(base + "/authentication/flows")
        login = next(f for f in flows if f["alias"] == login_alias)
        wrapper = next(f for f in flows if f["alias"] == wrapper_alias)
        kc.post(base + "/authentication/executions", {"parentFlow": wrapper["id"],
            "flowId": login["id"], "authenticatorFlow": True, "requirement": "REQUIRED", "priority": 10})
        kc.post(base + "/authentication/flows/" + q(wrapper_alias) + "/executions/execution",
                {"provider": PROVIDER, "priority": 20})
        executions = kc.get(base + "/authentication/flows/" + q(wrapper_alias) + "/executions")
        gate = next(e for e in executions if e.get("providerId") == PROVIDER)
        gate["requirement"] = "REQUIRED"
        kc.put(base + "/authentication/flows/" + q(wrapper_alias) + "/executions", gate)
        attrs[FLOW_ID] = wrapper["id"]
    attrs[GROUP_ID] = group["id"]
    attrs[GROUP_PATH] = group["path"]
    client.setdefault("authenticationFlowBindingOverrides", {})["browser"] = attrs[FLOW_ID]
    client.update({"directAccessGrantsEnabled": False, "implicitFlowEnabled": False,
        "serviceAccountsEnabled": False})
    kc.put(base + "/clients/" + q(client["id"]), client)
    models = base + "/clients/" + q(client["id"]) + "/protocol-mappers/models"
    if not any(m.get("protocolMapper") == TOKEN_GATE for m in kc.get(models)):
        kc.post(models, {"name": "ns8-required-group", "protocol": "openid-connect",
            "protocolMapper": TOKEN_GATE, "config": {}})
    state = access_state(kc, realm, client)
    if not state["enforced"]:
        raise ValueError("Policy validation failed; client remains disabled")
    client["enabled"] = was_enabled
    kc.put(base + "/clients/" + q(client["id"]), client)
    return state
