from marvin.audit import GENESIS, Audit


def test_hash_chain_and_signature(tmp_path):
    a = Audit(str(tmp_path), "secret", idle_seconds=1)
    a.join("demo", "maria", name="Maria")
    a.append("demo", "turn", "maria", {"question": "ship it"})
    a.append("demo", "permission", "bob", {"allow": True})
    a.leave("demo", "maria")
    path = a.close("demo")
    assert path and path.exists() and path.with_suffix(".sig").exists()
    data = a.read(path.stem, admin=True)
    assert data and data["signed"] is True
    assert all(r["chain_ok"] for r in data["records"])
    assert data["records"][0]["prev"] == GENESIS
    assert data["records"][0]["verb"] == "session_start"
    assert a.verify_turn(path.stem, "maria", 1)
    assert not a.verify_turn(path.stem, "maria", 9)
    rows = a.list(admin=True)
    assert rows and rows[0]["id"] == path.stem


def test_participant_cannot_read_others_session(tmp_path):
    a = Audit(str(tmp_path), "secret")
    a.join("demo", "maria")
    a.leave("demo", "maria")
    path = a.close("demo")
    assert a.read(path.stem, who="bob", admin=False) is None
    assert a.read(path.stem, who="maria", admin=False)


def test_idle_close_and_retention(tmp_path):
    now = [1_800_000_000.0]
    closed = []
    a = Audit(str(tmp_path), "secret", now=lambda: now[0], idle_seconds=10, on_close=lambda m, p: closed.append(p))
    a.join("demo", "maria")
    a.leave("demo", "maria")
    assert a.close_if_idle() == []
    now[0] = 1_800_000_011
    assert a.close_if_idle() == ["demo"] and closed
    a.set_retention(1)
    old = tmp_path / "audit" / "demo" / "ancient.jsonl"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("{}\n")
    import os
    os.utime(old, (now[0] - 3 * 86400, now[0] - 3 * 86400))
    assert a.prune() >= 1
    assert not old.exists()
