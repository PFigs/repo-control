from repo_control import state


def test_sidecar_name():
    assert state.sidecar_name(real="feat/x") == "claude/feat/x"


def test_real_from_sidecar_roundtrip():
    assert state.real_from_sidecar(sidecar="claude/feat/x") == "feat/x"


def test_real_from_sidecar_is_noop_on_plain_branch():
    assert state.real_from_sidecar(sidecar="main") == "main"


def test_is_sidecar():
    assert state.is_sidecar(branch="claude/x") is True
    assert state.is_sidecar(branch="x") is False
