from repo_control import selection


def test_load_selection_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert selection.load_selection() is None


def test_save_then_load_round_trips(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    repos = {("anthropic", "sdk"), ("acme", "widgets")}
    selection.save_selection(repos)
    assert selection.load_selection() == repos


def test_save_empty_selection_is_not_remembered(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    selection.save_selection(set())
    assert not selection.selection_path().exists()
    assert selection.load_selection() is None


def test_load_corrupt_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = selection.selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json")
    assert selection.load_selection() is None


def test_load_file_without_repos_key_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = selection.selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"other": []}')
    assert selection.load_selection() is None


def test_load_repos_not_a_list_returns_none(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = selection.selection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"repos": "a/b"}')
    assert selection.load_selection() is None


def test_preselected_keys_no_memory_returns_none():
    assert selection.preselected_keys(last=None, available={("a", "b")}) is None


def test_preselected_keys_intersects_with_available():
    last = {("a", "b"), ("c", "d"), ("gone", "repo")}
    available = {("a", "b"), ("c", "d"), ("new", "repo")}
    assert selection.preselected_keys(last=last, available=available) == {"a/b", "c/d"}


def test_preselected_keys_stale_memory_returns_none():
    last = {("old", "one")}
    available = {("new", "two")}
    assert selection.preselected_keys(last=last, available=available) is None
