package com.example.idp;

import java.util.List;
import org.keycloak.Config;
import org.keycloak.authentication.Authenticator;
import org.keycloak.authentication.AuthenticatorFactory;
import org.keycloak.models.AuthenticationExecutionModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;
import org.keycloak.provider.ProviderConfigProperty;

public final class GroupGateFactory implements AuthenticatorFactory {
    public static final String ID = "ns8-client-group-gate";
    private static final Authenticator INSTANCE = new GroupGate();
    @Override public Authenticator create(KeycloakSession s) { return INSTANCE; }
    @Override public String getId() { return ID; }
    @Override public String getDisplayType() { return "NS8 required client group"; }
    @Override public String getHelpText() { return "Deny unless current LDAP membership matches the administrator-owned client group ID"; }
    @Override public String getReferenceCategory() { return null; }
    @Override public boolean isConfigurable() { return false; }
    @Override public AuthenticationExecutionModel.Requirement[] getRequirementChoices() {
        return new AuthenticationExecutionModel.Requirement[] {AuthenticationExecutionModel.Requirement.REQUIRED};
    }
    @Override public boolean isUserSetupAllowed() { return false; }
    @Override public List<ProviderConfigProperty> getConfigProperties() { return List.of(); }
    @Override public void init(Config.Scope c) { }
    @Override public void postInit(KeycloakSessionFactory f) { }
    @Override public void close() { }
}
