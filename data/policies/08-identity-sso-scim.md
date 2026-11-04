---
doc_id: IAM
title: Identity, SSO & SCIM
version: 1.6
owner: Head of Engineering
last_reviewed: 2026-06-30
---

# Identity, SSO & SCIM

## IAM-1 Single sign-on
Acme Workspace supports SAML 2.0 and OpenID Connect single sign-on with any standards-compliant identity provider. Administrators can enforce SSO for all users in the tenant.

## IAM-2 Provisioning
SCIM 2.0 provisioning and de-provisioning is supported on Enterprise plans. Removing a user in the identity provider revokes their access to Acme Workspace on the next sync.

## IAM-3 Native login
Where SSO is not used, passwords must be at least 12 characters and are checked against known-breached password lists. Passwords are hashed using bcrypt. Users can enable MFA via authenticator app, and administrators can make it mandatory.

## IAM-4 Roles and permissions
Acme Workspace provides role-based access control with Owner, Admin, Member and Guest roles, plus document-level permissions. Administrators can view an audit log of logins, permission changes and exports.

## IAM-5 Sessions
Session timeout is configurable by administrators between 1 hour and 30 days. Administrators can terminate all active sessions for a user.
