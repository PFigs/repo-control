from repo_control import picker
from repo_control.picker import Choice


def _choices():
    return [Choice(key="a/b", label="a/b"), Choice(key="c/d", label="c/d")]


def test_select_multi_default_selected_true_returns_all(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert picker.select_multi(title="t", choices=_choices()) == ["a/b", "c/d"]


def test_select_multi_default_selected_false_returns_empty(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert picker.select_multi(title="t", choices=_choices(), default_selected=False) == []


def test_select_multi_preselected_keys_filters(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = picker.select_multi(title="t", choices=_choices(), preselected_keys={"a/b"})
    assert result == ["a/b"]


def test_select_multi_preselected_keys_override_default_selected(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = picker.select_multi(
        title="t", choices=_choices(), default_selected=False, preselected_keys={"a/b"}
    )
    assert result == ["a/b"]


def test_select_multi_empty_choices():
    assert picker.select_multi(title="t", choices=[]) == []
