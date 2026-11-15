# Filters over group_vars/all/devices.yaml and network.yaml, for docs.yaml. Plain Python with
# the stdlib ipaddress, since Ansible's ip filters need netaddr. Tested by scripts/network.test.py.
import ipaddress
import re


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
    macs = {}
    for name, device in devices.items():
        for port, spec in (device.get("ports") or {}).items():
            for net in ([spec["native"]] if "native" in spec else []) + spec.get("tagged", []):
                if net not in networks:
                    errors.append(f"Port {name}:{port}: unknown Network {net}")
            if spec.get("mac"):  # "" is a placeholder
                mac = str(spec["mac"]).lower()
                if not re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", mac):
                    errors.append(f"Port {name}:{port}: mac {spec['mac']!r} isn't aa:bb:cc:dd:ee:ff")
                elif mac in macs:
                    errors.append(f"Port {name}:{port}: mac {mac} is also on {macs[mac]}")
                macs[mac] = f"{name}:{port}"
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


def _routed(networks):
    return {net: spec for net, spec in networks.items() if "gateway" in spec}


def router_interfaces(networks, ports, port_devices, router):
    """Each Network `router` is the gateway of -> its OS device (a VLAN on the parent's device
    when tagged), the router's address as CIDR, and the Kea pool when it has dhcp."""
    out = []
    for port, spec in ports.items():
        nets = [(spec["native"], None)] if "native" in spec else []
        nets += [(net, networks[net]["vlan"]) for net in spec.get("tagged", [])]
        for net, vlan in nets:
            n = networks[net]
            if n.get("gateway") != router:
                continue
            cidr = ipaddress.ip_network(n["cidr"])
            iface = {"network": net, "cidr": n["cidr"], "ip": _addr(n["addresses"][router]),
                     "addr": f"{_addr(n['addresses'][router])}/{cidr.prefixlen}",
                     "device": f"vlan0.{vlan}" if vlan else port_devices[port]}
            if vlan:
                iface.update(vlan=vlan, parent=port_devices[port])
            if n.get("dhcp"):
                base = cidr.network_address
                iface["pool"] = f"{base + n['dhcp']['from']} - {base + n['dhcp']['to']}"
            out.append(iface)
    return out


def dhcp_reservations(networks):
    """Every address with a real mac, as a Kea reservation; TODO placeholders are skipped."""
    return [{"network": net, "subnet": spec["cidr"], "hostname": name, "ip": value["addr"],
             "mac": value["mac"].lower()}
            for net, spec in _routed(networks).items() if spec.get("dhcp")
            for name, value in (spec.get("addresses") or {}).items()
            if isinstance(value, dict) and re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", str(value.get("mac", "")).lower())]


def dns_hosts(networks, home_domain):
    """The DNS rule in network.yaml as Unbound overrides: <name>.<network>.<home_domain> for every
    address on a routed Network, plus <name>.<home_domain> for a name with exactly one."""
    routed = _routed(networks)
    count = {}
    for spec in routed.values():
        for name in spec.get("addresses") or {}:
            count[name] = count.get(name, 0) + 1
    out = []
    for net, spec in routed.items():
        for name, value in (spec.get("addresses") or {}).items():
            out.append({"hostname": name, "domain": f"{net}.{home_domain}", "value": _addr(value)})
            if count[name] == 1:
                out.append({"hostname": name, "domain": home_domain, "value": _addr(value)})
    return out


class FilterModule:
    def filters(self):
        return {"network_errors": network_errors, "cable_peers": cable_peers,
                "router_interfaces": router_interfaces, "dhcp_reservations": dhcp_reservations,
                "dns_hosts": dns_hosts}
