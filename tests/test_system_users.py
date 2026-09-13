from system_users import MANAGER_ROLES, ROLE_ACCESS_ADMIN, ROLE_MANAGER, normalize_id_number


def test_normalize_id_number_pads_leading_zeroes():
    assert normalize_id_number("12345678") == "012345678"


def test_normalize_id_number_ignores_common_separators():
    assert normalize_id_number("12-345-678") == "012345678"


def test_manager_roles_include_manager_and_permission_admin():
    assert ROLE_MANAGER in MANAGER_ROLES
    assert ROLE_ACCESS_ADMIN in MANAGER_ROLES
