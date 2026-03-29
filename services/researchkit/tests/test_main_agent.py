from researchkit.agents.patch_utils import compute_minimal_edit


def test_compute_minimal_edit_for_mid_file_change():
    before = "alpha\nbeta\ncharlie\n"
    after = "alpha\nbeta updated\ncharlie\n"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == len("alpha\nbeta")
    assert selection_to == len("alpha\nbeta")
    assert original_text == ""
    assert replacement_text == " updated"


def test_compute_minimal_edit_for_full_replacement():
    before = "old text"
    after = "new text"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == 0
    assert selection_to == 3
    assert original_text == "old"
    assert replacement_text == "new"


def test_compute_minimal_edit_for_deletion():
    before = "abc123xyz"
    after = "abcxyz"

    selection_from, selection_to, original_text, replacement_text = (
        compute_minimal_edit(before, after)
    )

    assert selection_from == 3
    assert selection_to == 6
    assert original_text == "123"
    assert replacement_text == ""
