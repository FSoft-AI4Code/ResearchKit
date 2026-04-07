def compute_minimal_edit(before: str, after: str) -> tuple[int, int, str, str]:
    prefix_len = 0
    max_prefix = min(len(before), len(after))
    while prefix_len < max_prefix and before[prefix_len] == after[prefix_len]:
        prefix_len += 1

    before_remaining = len(before) - prefix_len
    after_remaining = len(after) - prefix_len
    suffix_len = 0
    max_suffix = min(before_remaining, after_remaining)
    while (
        suffix_len < max_suffix
        and before[len(before) - suffix_len - 1] == after[len(after) - suffix_len - 1]
    ):
        suffix_len += 1

    before_end = len(before) - suffix_len
    after_end = len(after) - suffix_len
    return (
        prefix_len,
        before_end,
        before[prefix_len:before_end],
        after[prefix_len:after_end],
    )
