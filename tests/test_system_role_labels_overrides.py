from system_role_labels_overrides import (
    LEGACY_ROLE_ACCESS_ADMIN,
    ROLE_ACCESS_ADMIN_LABEL,
    normalize_role_label,
)


def test_permission_admin_role_gets_clearer_display_label():
    assert normalize_role_label(LEGACY_ROLE_ACCESS_ADMIN) == ROLE_ACCESS_ADMIN_LABEL
    assert ROLE_ACCESS_ADMIN_LABEL == "מנהל/ת מערכת + ניהול הרשאות"


def test_other_roles_are_unchanged():
    assert normalize_role_label("מנהל/ת מערכת") == "מנהל/ת מערכת"
    assert normalize_role_label("עובד/ת") == "עובד/ת"
