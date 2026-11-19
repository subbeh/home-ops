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


def gatus_endpoints(networks, devices):
    """An ICMP Gatus endpoint per address on a routed Network, named like its DNS name, unless
    the address or its Device says `monitor: false`. Gatus runs on the vps, so these ping over
    the tailnet routes."""
    return [{"name": f"{name}.{net}", "group": "home", "url": f"icmp://{_addr(value)}", "interval": "5m",
             "conditions": ["[CONNECTED] == true"], "alerts": [{"type": "pushover", "send-on-resolved": True}]}
            for net, spec in _routed(networks).items()
            for name, value in (spec.get("addresses") or {}).items()
            if not (isinstance(value, dict) and value.get("monitor") is False)
            and devices.get(name, {}).get("monitor") is not False]


def ingress_routes(hostvars, hosts, services_configs, networks):
    """A route per Service with an `ingress:` port assigned to one of hosts: the home ingress
    (HAProxy on OPNsense) forwards <service>.<ingress_domain> to that port on the Host's servers
    address. An assigned Service without a file is skipped: a private one's is only in the main
    checkout."""
    routes = [{"service": name, "address": networks["servers"]["addresses"][host],
               "port": services_configs[name]["ingress"]["port"]}
              for host in hosts
              for name in hostvars[host].get("services") or []
              if "ingress" in (services_configs.get(name) or {})]
    names = [r["service"] for r in routes]
    if len(names) != len(set(names)):
        raise ValueError(f"routed from more than one Host: {sorted({n for n in names if names.count(n) > 1})}")
    return routes


def ingress_gatus_endpoints(routes, domain, resolver):
    """An HTTPS Gatus endpoint per ingress route. The names have no public record, so Gatus asks
    OPNsense's Unbound at resolver."""
    return [{"name": r["service"], "group": "ingress", "url": f"https://{r['service']}.{domain}",
             "client": {"dns-resolver": f"tcp://{resolver}:53"}, "conditions": ["[STATUS] == 200"],
             "alerts": [{"type": "pushover", "send-on-resolved": True}]}
            for r in routes]


def _alias(name):
    """OPNsense alias names allow letters, digits and underscores only."""
    return name.replace("-", "_")


def firewall_aliases(networks, pools):
    """A network alias per Network and Pool, a host alias per name in their addresses, and
    `home` with every Network and Pool, which a rule inverts to mean the internet. `home` lists
    CIDRs rather than nesting the aliases: the module rejects members that don't exist yet."""
    cidrs = {**{n: s["cidr"] for n, s in networks.items()}, **{p: s["cidr"] for p, s in pools.items()}}
    hosts = {}
    for spec in networks.values():
        for name, value in (spec.get("addresses") or {}).items():
            hosts.setdefault(name, []).append(_addr(value))
    out = [{"name": _alias(n), "type": "network", "content": [c], "description": f"{n} in network.yaml"}
           for n, c in cidrs.items()]
    out += [{"name": _alias(n), "type": "host", "content": a, "description": f"{n} in network.yaml"}
            for n, a in hosts.items()]
    out.append({"name": "home", "type": "network", "content": list(cidrs.values()),
                "description": "Every Network and Pool in network.yaml"})
    names = [a["name"] for a in out]
    if len(names) != len(set(names)):
        raise ValueError(f"duplicate alias names: {sorted({n for n in names if names.count(n) > 1})}")
    return out


def firewall_rules(rules, interfaces, ids):
    """`rules` from host_vars as oxlorg.opnsense.rule args, plus DNS to OPNsense's own address
    from each routed Network. `interfaces` lists {network, device} and `ids` maps a device to its
    interface identifier; a Network not assigned yet (a first --check run) is skipped. In a rule,
    `source` defaults to the Network and `destination: internet` means anything outside `home`."""
    net_ids = {i["network"]: ids[i["device"]] for i in interfaces if i["device"] in ids}
    dns = [{"network": i["network"], "destination": f"{net_ids[i['network']]}ip", "port": "53",
            "protocol": "TCP/UDP", "description": f"{i['network']}: DNS"}
           for i in interfaces if "ip" in i and i["network"] in net_ids]
    out = []
    for rule in dns + rules:
        if rule["network"] not in net_ids:
            continue
        dest = rule.get("destination", "any")
        out.append({"description": rule["description"], "interface": [net_ids[rule["network"]]],
                    "source_net": _alias(rule.get("source", rule["network"])),
                    "destination_net": "home" if dest == "internet" else _alias(dest),
                    "destination_invert": dest == "internet",
                    "destination_port": rule.get("port", ""), "protocol": rule.get("protocol", "any")})
    return out


class FilterModule:
    def filters(self):
        return {"network_errors": network_errors, "cable_peers": cable_peers,
                "router_interfaces": router_interfaces, "dhcp_reservations": dhcp_reservations,
                "dns_hosts": dns_hosts, "gatus_endpoints": gatus_endpoints,
                "ingress_routes": ingress_routes, "ingress_gatus_endpoints": ingress_gatus_endpoints,
                "firewall_aliases": firewall_aliases,
                "firewall_rules": firewall_rules}
