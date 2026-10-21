# Filters over group_vars/all/devices.yaml and network.yaml, for docs.yaml. Plain Python with
# the stdlib ipaddress, since Ansible's ip filters need netaddr. Tested by scripts/network.test.py.
import ipaddress


def _panel(devices, end):
    """The patch panel and its Port when `end` is one side of a panel Port, else None."""
    device, _, port = end.partition(":")
    port, _, side = port.partition("/")
    if devices.get(device, {}).get("kind") == "patch-panel" and side in ("front", "back"):
        return device, port, side
    return None


def _ports(devices):
    """Every Port as 'device:port' -> kind. A panel Port exists as <port>/front and <port>/back."""
    ports = {}
    for name, device in devices.items():
        sides = ("/front", "/back") if device["kind"] == "patch-panel" else ("",)
        for port, spec in (device.get("ports") or {}).items():
            for side in sides:
                ports[f"{name}:{port}{side}"] = spec["kind"]
    return ports


def _addr(value):
    return value["addr"] if isinstance(value, dict) else value


def network_errors(devices, networks, cables, pools, ssids, tailnet_routes, hosts):
    """Every problem in the network source files, one message each; empty when valid."""
    errors = []
    ports = _ports(devices)

    used = {}
    for cable in cables:
        a, b = str(cable["a"]), str(cable["b"])
        for end in (a, b):
            if end not in ports:
                errors.append(f"Cable {a} -- {b}: unknown Port {end}")
            elif end in used:
                errors.append(f"Port {end} has two Cables: to {used[end]} and to {b if end == a else a}")
            else:
                used[end] = b if end == a else a
        if a in ports and b in ports and ports[a] != ports[b]:
            errors.append(f"Cable {a} -- {b}: joins {ports[a]} to {ports[b]}")

    seen = {}
    for net, spec in networks.items():
        cidr = ipaddress.ip_network(spec["cidr"])
        addresses = spec.get("addresses") or {}
        dhcp = spec.get("dhcp")
        if "gateway" in spec and spec["gateway"] not in addresses:
            errors.append(f"Network {net}: gateway {spec['gateway']} has no address on it")
        if dhcp and "gateway" not in spec:
            errors.append(f"Network {net}: unrouted, but has dhcp")
        for name, value in addresses.items():
            where = f"{net}.addresses.{name}"
            try:
                ip = ipaddress.ip_address(_addr(value))
            except ValueError:
                errors.append(f"{where}: {_addr(value)!r} is not an IP address")
                continue
            if ip not in cidr:
                errors.append(f"{where}: {ip} is outside {cidr}")
            if ip in seen:
                errors.append(f"{where}: {ip} is also {seen[ip]}")
            seen[ip] = where
            host = int(ip) - int(cidr.network_address)
            if dhcp and not (isinstance(value, dict) and "mac" in value) and dhcp["from"] <= host <= dhcp["to"]:
                errors.append(f"{where}: static {ip} is inside the dhcp range")

    for pool, spec in pools.items():
        for net, net_spec in networks.items():
            if ipaddress.ip_network(spec["cidr"]).overlaps(ipaddress.ip_network(net_spec["cidr"])):
                errors.append(f"Pool {pool}: {spec['cidr']} overlaps Network {net}")

    for ssid, net in ssids.items():
        if net not in networks:
            errors.append(f"SSID {ssid}: unknown Network {net}")
    for name, device in devices.items():
        for port, spec in (device.get("ports") or {}).items():
            for net in ([spec["native"]] if "native" in spec else []) + spec.get("tagged", []):
                if net not in networks:
                    errors.append(f"Port {name}:{port}: unknown Network {net}")
    for name in tailnet_routes:
        if name not in devices and name not in hosts:
            errors.append(f"tailnet_routes: unknown Device or Host {name}")
    return errors


def cable_peers(cables, devices):
    """Every Cable end -> {peer, via}: the far Port, traced through patch panels, and the
    panel Ports passed on the way. A run that stops at an empty panel side ends there."""
    other = {}
    for cable in cables:
        a, b = str(cable["a"]), str(cable["b"])
        other[a], other[b] = b, a
    peers = {}
    for end in other:
        peer, via = other[end], []
        while (panel := _panel(devices, peer)) and len(via) < len(other):
            device, port, side = panel
            through = f"{device}:{port}/{'back' if side == 'front' else 'front'}"
            if through not in other:
                break
            via.append(f"{device}:{port}")
            peer = other[through]
        peers[end] = {"peer": peer, "via": via}
    return peers


class FilterModule:
    def filters(self):
        return {"network_errors": network_errors, "cable_peers": cable_peers}
