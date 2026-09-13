"""Compatibility layer for clearer system-role labels.

The stored legacy role value "מנהל/ת הרשאות" is still accepted, but the UI and
new writes use the clearer label "מנהל/ת מערכת + ניהול הרשאות". This avoids a
breaking migration while keeping authorization semantics unchanged.
"""
from __future__ import annotations


LEGACY_ROLE_ACCESS_ADMIN = "מנהל/ת הרשאות"
ROLE_ACCESS_ADMIN_LABEL = "מנהל/ת מערכת + ניהול הרשאות"


def normalize_role_label(value: object) -> str:
    role = str(value or "").strip()
    if role == LEGACY_ROLE_ACCESS_ADMIN:
        return ROLE_ACCESS_ADMIN_LABEL
    return role


def install(app_module=None) -> None:
    import system_users

    if getattr(system_users, "_system_role_labels_override_installed", False):
        return

    original_list_users = system_users.list_users

    def list_users_with_normalized_roles(st):
        users = original_list_users(st)
        normalized = []
        for user in users:
            item = dict(user)
            item["role"] = normalize_role_label(item.get("role"))
            normalized.append(item)
        return normalized

    # Keep the original list/set objects alive where possible because entry_flow
    # imports them by reference during application startup.
    system_users.list_users = list_users_with_normalized_roles
    system_users.ROLE_ACCESS_ADMIN = ROLE_ACCESS_ADMIN_LABEL
    system_users.SYSTEM_ROLES[:] = [
        system_users.ROLE_EMPLOYEE,
        system_users.ROLE_MANAGER,
        ROLE_ACCESS_ADMIN_LABEL,
    ]
    system_users.MANAGER_ROLES.clear()
    system_users.MANAGER_ROLES.update(
        {
            system_users.ROLE_MANAGER,
            ROLE_ACCESS_ADMIN_LABEL,
        }
    )

    # entry_flow is imported before overrides are installed, so update its copied
    # constants as well. Existing sheet rows are normalized by list_users above.
    import entry_flow

    entry_flow.ROLE_ACCESS_ADMIN = ROLE_ACCESS_ADMIN_LABEL
    entry_flow.MANAGER_ROLES = system_users.MANAGER_ROLES

    # Tool 7 is safe to import here. Patch its copied role constants so all new
    # selections and writes use the clearer label.
    import tool7_system_users

    tool7_system_users.ROLE_ACCESS_ADMIN = ROLE_ACCESS_ADMIN_LABEL
    tool7_system_users.SYSTEM_ROLES[:] = system_users.SYSTEM_ROLES
    tool7_system_users.ADD_ROLE_OPTIONS[:] = [
        system_users.ROLE_MANAGER,
        ROLE_ACCESS_ADMIN_LABEL,
        system_users.ROLE_EMPLOYEE,
    ]

    # Normalize a manager session created before a hot reload.
    if app_module is not None:
        current = app_module.st.session_state.get(system_users.MANAGER_USER_SESSION_KEY)
        if isinstance(current, dict) and current.get("role") == LEGACY_ROLE_ACCESS_ADMIN:
            normalized_current = dict(current)
            normalized_current["role"] = ROLE_ACCESS_ADMIN_LABEL
            app_module.st.session_state[system_users.MANAGER_USER_SESSION_KEY] = normalized_current

    system_users._system_role_labels_override_installed = True
