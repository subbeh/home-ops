#!/usr/bin/env python3
# Self-test for ansible/playbooks/filter_plugins/network.py. Run with `just docs-test`.
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "ansible/playbooks/filter_plugins"))
import network  # noqa: E402

DEVICES = {
    "router": {"kind": "router", "ports": {
        "0": {"kind": "ethernet", "tagged": ["lan"]},
        "hdmi": {"kind": "hdmi"},
    }},
    "panel": {"kind": "patch-panel", "ports": {"1": {"kind": "ethernet"}, "2": {"kind": "ethernet"}}},
    "server": {"kind": "server", "ports": {"eth": {"kind": "ethernet"}}},
}
NETWORKS = {
    "lan": {"cidr": "10.0.0.0/24", "gateway": "router", "dhcp": {"from": 100, "to": 199},
            "addresses": {"router": "10.0.0.1", "server": {"addr": "10.0.0.150", "mac": "aa:bb"}}},
    "storage": {"cidr": "10.9.0.0/24", "addresses": {"server": "10.9.0.10"}},
}
CABLES = [
    {"a": "router:0", "b": "panel:1/back"},
    {"a": "panel:1/front", "b": "server:eth"},
]
POOLS = {"lb": {"cidr": "10.8.0.0/24"}}


def errors(**changes):
    args = copy.deepcopy({"devices": DEVICES, "networks": NETWORKS, "cables": CABLES, "pools": POOLS,
                          "ssids": {"wifi": "lan"}, "tailnet_routes": {"router": {}}, "hosts": ["vps"]})
    for path, value in changes.items():
        *keys, last = path.split("__")
        target = args
        for key in keys:
            target = target[int(key) if isinstance(target, list) else key]
        target[last] = value
    return network.network_errors(**args)


class NetworkErrors(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(errors(), [])

    def assertError(self, text, **changes):
        found = errors(**changes)
        self.assertTrue(any(text in e for e in found), f"no {text!r} in {found}")

    def test_cables(self):
        self.assertError("unknown Port router:9", cables__0__a="router:9")
        self.assertError("unknown Port panel:1", cables__0__b="panel:1")
        self.assertError("joins hdmi to ethernet", cables__0__a="router:hdmi")
        self.assertError("has two Cables", cables=CABLES + [{"a": "server:eth", "b": "panel:2/front"}])

    def test_addresses(self):
        self.assertError("outside 10.0.0.0/24", networks__lan__addresses__router="10.0.1.1")
        self.assertError("is not an IP address", networks__lan__addresses__router="TODO(you)")
        self.assertError("is also lan.addresses.router", networks__storage__addresses__server="10.0.0.1")
        self.assertError("inside the dhcp range", networks__lan__addresses__server="10.0.0.150")

    def test_gateways(self):
        self.assertError("gateway router has no address", networks__storage__gateway="router")
        self.assertError("unrouted, but has dhcp", networks__storage__dhcp={"from": 1, "to": 2})

    def test_names(self):
        self.assertError("overlaps Network lan", pools__lb__cidr="10.0.0.128/25")
        self.assertError("SSID wifi: unknown Network", ssids={"wifi": "guest"})
        self.assertError("Port router:0: unknown Network", devices__router__ports__0__tagged=["guest"])
        self.assertError("unknown Device or Host nope", tailnet_routes={"nope": {}})


class CablePeers(unittest.TestCase):
    def test_traces_through_panels(self):
        peers = network.cable_peers(CABLES, DEVICES)
        self.assertEqual(peers["router:0"], {"peer": "server:eth", "via": ["panel:1"]})
        self.assertEqual(peers["panel:1/front"], {"peer": "server:eth", "via": []})

    def test_stops_at_an_empty_panel_side(self):
        peers = network.cable_peers(CABLES[:1], DEVICES)
        self.assertEqual(peers["router:0"], {"peer": "panel:1/back", "via": []})


if __name__ == "__main__":
    unittest.main()
