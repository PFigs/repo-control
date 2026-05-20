from repo_control import picker, selection
from repo_control.__main__ import _select_repos_interactive


def _by_repo():
    return {("a", "b"): {1: None, 2: None}, ("c", "d"): {1: None}}


def test_single_repo_returns_all_without_saving(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    result = _select_repos_interactive(by_repo=_by_repo(), single_repo=("a", "b"))
    assert result == {("a", "b"), ("c", "d")}
    assert not selection.selection_path().exists()


def test_non_tty_returns_all_without_saving(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    result = _select_repos_interactive(by_repo=_by_repo(), single_repo=None)
    assert result == {("a", "b"), ("c", "d")}
    assert not selection.selection_path().exists()


def test_interactive_pick_is_saved(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(picker, "select_multi", lambda **kwargs: ["a/b"])
    result = _select_repos_interactive(by_repo=_by_repo(), single_repo=None)
    assert result == {("a", "b")}
    assert selection.load_selection() == {("a", "b")}


def test_cancelled_pick_returns_none_without_saving(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr(picker, "select_multi", lambda **kwargs: None)
    result = _select_repos_interactive(by_repo=_by_repo(), single_repo=None)
    assert result is None
    assert not selection.selection_path().exists()


def test_saved_selection_is_passed_as_preselected(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    selection.save_selection({("c", "d")})
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    captured = {}

    def fake_select_multi(**kwargs):
        captured.update(kwargs)
        return ["c/d"]

    monkeypatch.setattr(picker, "select_multi", fake_select_multi)
    _select_repos_interactive(by_repo=_by_repo(), single_repo=None)
    assert captured["preselected_keys"] == {"c/d"}


def test_first_run_has_no_preselection(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    captured = {}

    def fake_select_multi(**kwargs):
        captured.update(kwargs)
        return ["a/b", "c/d"]

    monkeypatch.setattr(picker, "select_multi", fake_select_multi)
    _select_repos_interactive(by_repo=_by_repo(), single_repo=None)
    assert captured["preselected_keys"] is None
