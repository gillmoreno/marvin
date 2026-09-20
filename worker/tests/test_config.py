import pytest

from marvin.config import load_config


def test_load_rooms(tmp_path):
    f = tmp_path / "rooms.yaml"
    f.write_text("""
rooms:
  - name: backend
    repo: /work/repos/backend
    git_url: git@github.com:acme/backend.git
    branch: main
    language: en
    app_links:
      - { label: frontend, url: https://backend.example.com, port: 3000 }
      - { label: docs, url: https://docs.example.com }
  - name: marvin
    repo: /work/repos/marvin
    harness: opencode
""")
    cfg = load_config(f)
    assert [r.name for r in cfg.rooms] == ["backend", "marvin"]
    ox = cfg.room("backend")
    assert ox.git_url.endswith("backend.git") and ox.branch == "main" and ox.language == "en"
    assert ox.harness is None and cfg.room("marvin").harness == "opencode"
    assert ox.app_links[0].host == "backend.example.com" and ox.app_links[0].port == 3000
    assert ox.app_links[1].port is None
    assert ox.app_links[0].to_wire() == {"label": "frontend", "url": "https://backend.example.com"}
    assert cfg.room("nope") is None


def test_blank_language_is_autodetect(tmp_path):
    f = tmp_path / "rooms.yaml"
    f.write_text("rooms:\n  - {name: a, repo: /x, language: ''}\n  - {name: b, repo: /y, language: auto}\n")
    cfg = load_config(f)
    assert cfg.room("a").language is None
    assert cfg.room("b").language is None


def test_duplicate_room_names_rejected(tmp_path):
    f = tmp_path / "rooms.yaml"
    f.write_text("rooms:\n  - {name: a, repo: /x}\n  - {name: a, repo: /y}\n")
    with pytest.raises(ValueError):
        load_config(f)
