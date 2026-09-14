from tool4_central_schedule_overrides import _identified_employee_name


class _FakeStreamlit:
    def __init__(self, session_state):
        self.session_state = session_state


def test_identified_employee_uses_exact_full_name():
    st = _FakeStreamlit(
        {
            "medstaff_identified_worker_v1": {
                "full_name": "יאיר חזקיהו שטיינברג",
                "first_name": "יאיר",
            }
        }
    )
    names = ["נועה", "יאיר חזקיהו שטיינברג", "עומר"]
    assert _identified_employee_name(st, names) == "יאיר חזקיהו שטיינברג"


def test_identified_employee_can_use_unique_first_name_schedule_label():
    st = _FakeStreamlit(
        {
            "medstaff_identified_worker_v1": {
                "full_name": "יאיר חזקיהו שטיינברג",
                "first_name": "יאיר",
            }
        }
    )
    names = ["נועה", "יאיר", "עומר"]
    assert _identified_employee_name(st, names) == "יאיר"


def test_identified_employee_never_falls_back_to_someone_else():
    st = _FakeStreamlit(
        {
            "medstaff_identified_worker_v1": {
                "full_name": "יאיר חזקיהו שטיינברג",
                "first_name": "יאיר",
            }
        }
    )
    assert _identified_employee_name(st, ["נועה", "עומר"]) == ""


def test_manager_mode_has_no_identified_employee():
    st = _FakeStreamlit({})
    assert _identified_employee_name(st, ["נועה", "עומר"]) is None
