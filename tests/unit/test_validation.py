import pytest

from projects_api.domain.validation import (
    NAME_MAX_LENGTH,
    NAME_MIN_LENGTH,
    name_key,
    validate_name,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("my-first-agent", "my-first-agent"),
        ("  padded name  ", "padded name"),
        ("double  space   inside", "double space inside"),
        ("Under_Score 9", "Under_Score 9"),
        ("abc", "abc"),
        ("a" * NAME_MAX_LENGTH, "a" * NAME_MAX_LENGTH),
    ],
)
def test_valid_names_are_normalised(raw: str, expected: str) -> None:
    assert validate_name(raw) == expected


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ("ab", "at least"),
        ("  a  ", "at least"),
        ("a" * (NAME_MAX_LENGTH + 1), "at most"),
        ("-leading-hyphen", "start and end"),
        ("trailing-hyphen-", "start and end"),
        ("bad/slash", "only contain"),
        ("bad.dot", "only contain"),
        ("emoji 🚀", "only contain"),
        ("semi;colon", "only contain"),
        ("<script>", "only contain"),
    ],
)
def test_invalid_names_raise(raw: str, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        validate_name(raw)


def test_min_length_constant_is_sane() -> None:
    assert 1 <= NAME_MIN_LENGTH < NAME_MAX_LENGTH <= 63


@pytest.mark.parametrize(
    "a, b",
    [
        ("My Project", "my project"),
        ("  My   Project ", "my project"),
        ("ALL-CAPS", "all-caps"),
    ],
)
def test_name_key_is_case_and_whitespace_insensitive(a: str, b: str) -> None:
    assert name_key(a) == name_key(b)
