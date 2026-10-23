package com.example.idp;

import org.keycloak.models.ClientModel;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;

/** Shared live LDAP check for browser authorization and token issuance. */
public final class GroupAccess {
    private GroupAccess() { }
    public static boolean allowed(RealmModel realm, ClientModel client, UserModel user) {
        try {
            var groupId = client.getAttribute(GroupGate.GROUP_ID);
            var group = groupId == null ? null : realm.getGroupById(groupId);
            var federation = user == null || user.getFederationLink() == null
                ? null : realm.getComponent(user.getFederationLink());
            boolean liveLdap = federation != null && "ldap".equals(federation.getProviderId())
                && "NO_CACHE".equals(federation.getConfig().getFirst("cachePolicy"))
                && "READ_ONLY".equals(federation.getConfig().getFirst("editMode"))
                && realm.getComponentsStream(federation.getId(),
                    "org.keycloak.storage.ldap.mappers.LDAPStorageMapper")
                    .anyMatch(m -> "group-ldap-mapper".equals(m.getProviderId())
                        && "READ_ONLY".equals(m.getConfig().getFirst("mode"))
                        && "LOAD_GROUPS_BY_MEMBER_ATTRIBUTE".equals(
                            m.getConfig().getFirst("user.roles.retrieve.strategy")));
            // getGroupsStream on the read-only LDAP mapper loads current member
            // attributes. Do not grant via local client roles or user-editable claims.
            return group != null && user != null && liveLdap
                && user.getGroupsStream().anyMatch(g -> g.getId().equals(groupId));
        } catch (RuntimeException ex) {
            return false;
        }
    }
}
