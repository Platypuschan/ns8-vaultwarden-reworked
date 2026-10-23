package com.example.idp;

import jakarta.ws.rs.core.Response;
import org.keycloak.authentication.AuthenticationFlowContext;
import org.keycloak.authentication.AuthenticationFlowError;
import org.keycloak.authentication.Authenticator;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.keycloak.models.UserModel;

/** Final REQUIRED step, after both cookie and password authentication.
 * Group IDs are administrator-owned client attributes; missing data denies.
 * The LDAP provider must use NO_CACHE and a READ_ONLY membership mapper.
 */
public final class GroupGate implements Authenticator {
    public static final String GROUP_ID = "ns8.required_group_id";
    public static final String GROUP_PATH = "ns8.required_group_path";

    @Override
    public void authenticate(AuthenticationFlowContext context) {
        boolean allowed = false;
        try {
            allowed = GroupAccess.allowed(context.getRealm(),
                context.getAuthenticationSession().getClient(), context.getUser());
        } catch (RuntimeException ex) {
            // LDAP failures must not fall back to imported local memberships.
            allowed = false;
        }
        if (allowed) {
            context.success();
        } else {
            context.failureChallenge(AuthenticationFlowError.ACCESS_DENIED,
                context.form().setError("accessDenied")
                    .createErrorPage(Response.Status.FORBIDDEN));
        }
    }
    @Override public void action(AuthenticationFlowContext context) { authenticate(context); }
    @Override public boolean requiresUser() { return true; }
    @Override public boolean configuredFor(KeycloakSession s, RealmModel r, UserModel u) { return true; }
    @Override public void setRequiredActions(KeycloakSession s, RealmModel r, UserModel u) { }
    @Override public void close() { }
}
