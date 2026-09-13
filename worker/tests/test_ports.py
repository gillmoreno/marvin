from marvin.ports import AppsRouting, listening_ports


def test_parse_proc_net_tcp(tmp_path):
    (tmp_path / "net").mkdir()
    (tmp_path / "net" / "tcp").write_text(
        "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
        "   0: 00000000:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 0\n"   # 3000 LISTEN
        "   1: 0100007F:1F90 00000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 1 0\n"   # 8080 (own) LISTEN
        "   2: 0100007F:1F41 0100007F:C350 01 00000000:00000000 00:00000000 00000000     0        0 1 0\n"   # 8001 ESTABLISHED
    )
    (tmp_path / "net" / "tcp6").write_text("header\n   0: 00000000000000000000000000000000:1F40 00000000000000000000000000000000:0000 0A 0 0 0 0 0 0 0 1 0\n")  # 8000
    assert listening_ports(str(tmp_path)) == {3000, 8000}


def test_routing_links():
    local = AppsRouting()
    assert local.link(3000)["url"] == "http://localhost:3000"
    prod = AppsRouting(domain="example.com", routed_ports=frozenset({3000, 8000}))
    assert prod.link(3000)["url"] == "https://marvin-3000.example.com"
    assert prod.link(6006)["url"] == "" and "no URL" in prod.link(6006)["label"]
    assert AppsRouting.from_env({"MARVIN_APPS_DOMAIN": "x.y", "MARVIN_APPS_PORTS": "3000, 8000"}).routed_ports == {3000, 8000}


def test_edge_host_is_a_child_of_the_ui():
    r = AppsRouting.from_env({"MARVIN_DOMAIN": "marvin.aigil.dev"})
    assert r.link(3000)["url"] == "https://p3000.marvin.aigil.dev"
    assert r.preview_pattern() == "https://p{port}.marvin.aigil.dev"
    assert r.allows_preview_host("p3000.marvin.aigil.dev")
    assert r.allows_preview_host("P3000.marvin.aigil.dev")
    assert not r.allows_preview_host("marvin.aigil.dev")
    assert not r.allows_preview_host("p3000.evil.example")
    assert not r.allows_preview_host("p8080.marvin.aigil.dev")  # worker's own port
    assert not r.allows_preview_host("foo.marvin.aigil.dev")


def test_apps_host_overrides_domain():
    r = AppsRouting.from_env({"MARVIN_DOMAIN": "marvin.example.com", "MARVIN_APPS_HOST": "voice.acme.test", "MARVIN_APPS_PREFIX": "app-"})
    assert r.link(5173)["url"] == "https://app-5173.voice.acme.test"
    assert r.allows_preview_host("app-5173.voice.acme.test")
