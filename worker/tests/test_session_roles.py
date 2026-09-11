from types import SimpleNamespace

from marvin.room.session import roles_of


def p(metadata):
    return SimpleNamespace(identity="x", name="X", metadata=metadata)


def test_roles_of():
    assert roles_of(p('{"roles": ["participant", "admin"]}')) == frozenset({"participant", "admin"})
    assert roles_of(p('{"roles": []}')) == frozenset()
    assert roles_of(p("")) == frozenset()
    assert roles_of(p(None)) == frozenset()
    assert roles_of(p("not json {")) == frozenset()
    assert roles_of(p('"a string"')) == frozenset()
    assert roles_of(p('{"roles": "admin"}')) == frozenset()  # not a list
    assert roles_of(p('{"other": 1}')) == frozenset()
