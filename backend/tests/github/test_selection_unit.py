import pytest
from pydantic import ValidationError

from app.modules.github.selection_schemas import RepoOption, SelectionUpdate
from app.modules.github.selection_service import matches_scope


@pytest.mark.parametrize(
    ("scope", "private", "expected"),
    [
        ("public", False, True),
        ("public", True, False),
        ("private", False, False),
        ("private", True, True),
        ("combined", False, True),
        ("combined", True, True),
    ],
)
def test_scope(scope, private, expected):
    repo = RepoOption(
        id=12,
        full_name="demo/repo",
        private=private,
        html_url="https://github.com/demo/repo",
    )
    assert matches_scope(repo, scope) is expected


def test_invalid_scope():
    with pytest.raises(ValidationError):
        SelectionUpdate(scope="invalid", repository_ids=[1])


def test_maximum_selection():
    with pytest.raises(ValidationError):
        SelectionUpdate(scope="public", repository_ids=list(range(501)))
