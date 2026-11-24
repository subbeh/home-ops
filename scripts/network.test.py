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

    def test_macs(self):
        self.assertEqual(errors(devices__server__ports__eth__mac="AA:BB:CC:00:11:22"), [])
        self.assertEqual(errors(devices__server__ports__eth__mac=""), [])
        self.assertError("isn't aa:bb:cc:dd:ee:ff", devices__server__ports__eth__mac="TODO(you)")
        ports = copy.deepcopy(DEVICES["router"]["ports"])
        ports["0"]["mac"] = ports["hdmi"]["mac"] = "aa:bb:cc:00:11:22"
        self.assertError("is also on router:0", devices__router__ports=ports)


class CablePeers(unittest.TestCase):
    def test_traces_through_panels(self):
        peers = network.cable_peers(CABLES, DEVICES)
        self.assertEqual(peers["router:0"], {"peer": "server:eth", "via": ["panel:1"]})
        self.assertEqual(peers["panel:1/front"], {"peer": "server:eth", "via": []})

    def test_stops_at_an_empty_panel_side(self):
        peers = network.cable_peers(CABLES[:1], DEVICES)
        self.assertEqual(peers["router:0"], {"peer": "panel:1/back", "via": []})


class OpnsenseFilters(unittest.TestCase):
    NETS = {**NETWORKS, "iot": {"cidr": "10.0.4.0/24", "vlan": 4, "gateway": "router",
                                "addresses": {"router": "10.0.4.1", "tv": {"addr": "10.0.4.5", "mac": "TODO(you)"}}}}

    def test_router_interfaces(self):
        ports = {"0": {"native": "lan", "tagged": ["iot"]}}
        got = network.router_interfaces(self.NETS, ports, {"0": "igc0"}, "router")
        self.assertEqual(got[0], {"network": "lan", "cidr": "10.0.0.0/24", "ip": "10.0.0.1", "addr": "10.0.0.1/24",
                                  "device": "igc0", "pool": "10.0.0.100 - 10.0.0.199"})
        self.assertEqual(got[1]["device"], "vlan0.4")
        self.assertEqual(got[1]["parent"], "igc0")
        self.assertNotIn("pool", got[1])

    def test_dhcp_reservations_skip_placeholders(self):
        nets = copy.deepcopy(self.NETS)
        nets["lan"]["addresses"]["server"]["mac"] = "AA:BB:CC:00:11:22"
        self.assertEqual(network.dhcp_reservations(nets), [{"network": "lan", "subnet": "10.0.0.0/24",
                         "hostname": "server", "ip": "10.0.0.150", "mac": "aa:bb:cc:00:11:22"}])

    def test_dns_hosts(self):
        got = {(h["hostname"], h["domain"]): h["value"] for h in network.dns_hosts(self.NETS, "home")}
        self.assertEqual(got[("server", "lan.home")], "10.0.0.150")
        self.assertEqual(got[("server", "home")], "10.0.0.150")  # storage is unrouted
        self.assertNotIn(("router", "home"), got)  # two routed addresses
        self.assertNotIn(("server", "storage.home"), got)

    def test_gatus_endpoints(self):
        nets = copy.deepcopy(self.NETS)
        nets["iot"]["addresses"]["router"] = {"addr": "10.0.4.1", "monitor": False}
        got = {e["name"]: e["url"] for e in network.gatus_endpoints(nets, {"server": {}})}
        self.assertEqual(got, {"router.lan": "icmp://10.0.0.1", "server.lan": "icmp://10.0.0.150",
                               "tv.iot": "icmp://10.0.4.5"})  # storage is unrouted
        self.assertEqual({e["group"] for e in network.gatus_endpoints(nets, {"server": {}})}, {"network"})
        got = [e["name"] for e in network.gatus_endpoints(nets, {"server": {"monitor": False}})]
        self.assertEqual(got, ["router.lan", "tv.iot"])

    def test_ingress_routes(self):
        hostvars = {"svc": {"services": ["web", "db", "private"]}, "bare": {}}
        hostvars["svc"]["services"].append("api")
        configs = {"web": {"ingress": {"port": 8080}}, "db": {},  # private's file is absent
                   "api": {"ingress": {"port": 9000, "check": "/health", "aliases": ["files"]}}}
        nets = {"servers": {"addresses": {"svc": "10.0.20.12"}}}
        routes = network.ingress_routes(hostvars, ["svc", "bare"], configs, nets)
        self.assertEqual(routes, [{"service": "web", "address": "10.0.20.12", "port": 8080, "check": "", "names": ["web"]},
                                  {"service": "api", "address": "10.0.20.12", "port": 9000, "check": "/health",
                                   "names": ["api", "files"]}])
        self.assertEqual([e["url"] for e in network.ingress_gatus_endpoints(routes, "svc.example", "100.1.1.1")],
                         ["https://web.svc.example", "https://api.svc.example/health"])
        self.assertEqual({e["group"] for e in network.ingress_gatus_endpoints(routes, "svc.example", "100.1.1.1")}, {"home"})
        configs["web"]["ingress"]["aliases"] = ["api"]  # an alias taking another Service's name
        with self.assertRaises(ValueError):
            network.ingress_routes(hostvars, ["svc", "bare"], configs, nets)
        del configs["web"]["ingress"]["aliases"]
        hostvars["bare"] = {"services": ["web"]}
        nets["servers"]["addresses"]["bare"] = "10.0.20.13"
        with self.assertRaises(ValueError):
            network.ingress_routes(hostvars, ["svc", "bare"], configs, nets)

    def test_firewall_aliases(self):
        got = {a["name"]: (a["type"], a["content"]) for a in network.firewall_aliases(self.NETS, {"k8s-lb": {"cidr": "10.8.0.0/24"}})}
        self.assertEqual(got["k8s_lb"], ("network", ["10.8.0.0/24"]))
        self.assertEqual(got["server"], ("host", ["10.0.0.150", "10.9.0.10"]))
        self.assertEqual(got["home"][1][-1], "10.8.0.0/24")
        with self.assertRaises(ValueError):
            network.firewall_aliases(self.NETS, {"server": {"cidr": "10.8.0.0/24"}})

    def test_firewall_rules(self):
        interfaces = [{"network": "lan", "device": "igc0", "ip": "10.0.0.1"},
                      {"network": "iot", "device": "vlan0.4", "ip": "10.0.4.1"},
                      {"network": "tailnet", "device": "tailscale0"}]
        rules = [{"network": "lan", "destination": "internet", "description": "lan: internet"},
                 {"network": "tailnet", "source": "any", "description": "tailnet: any"},
                 {"network": "lan", "destination": "pve-nuc", "port": "22", "description": "lan: ssh"}]
        got = {r["description"]: r for r in network.firewall_rules(rules, interfaces, {"igc0": "lan", "tailscale0": "opt2"})}
        self.assertNotIn("iot: DNS", got)  # not assigned yet
        self.assertEqual(got["lan: DNS"]["destination_net"], "lanip")
        self.assertEqual((got["lan: internet"]["destination_net"], got["lan: internet"]["destination_invert"]), ("home", True))
        self.assertEqual((got["tailnet: any"]["interface"], got["tailnet: any"]["source_net"]), (["opt2"], "any"))
        self.assertEqual(got["lan: ssh"]["destination_net"], "pve_nuc")
        self.assertNotIn("tailnet: DNS", got)


if __name__ == "__main__":
    unittest.main()
