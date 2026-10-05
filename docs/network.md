# Start with a useful home network

Use the Verizon router for Wi-Fi and guest separation, Pi-hole for DNS filtering,
and Kuma for health checks. These are native settings, not another management app.
The repository does not apply router, firewall, or tailnet policy automatically.
Keep dated observations in private `local/home-network.md` and use the existing
[acceptance matrix](home-security.md#access-acceptance-matrix).

## Get one personal device working first

1. Find the Pi and identify the exact Verizon router model and whether the service
   is Fios or cellular Home Internet. Record the Pi's actual address, login,
   installed project, storage, and recovery connection using [TODO](TODO.md).
2. Give the Pi a stable address using a reservation in the router. Name the known
   devices in its connected-device list. Record personal, employer-managed,
   guest, and smart devices separately; preserve employer DNS/VPN policies.
3. Complete [recovery](recovery.md) and core deployment verification before
   changing client DNS. Save the original client settings for rollback. On one
   personal device, set DNS to the Pi's actual LAN address; leave the rest of the
   household unchanged. IPv6 DNS distribution needs its own check.
4. Confirm normal browsing, permitted DNS queries over UDP and TCP, and a harmless
   controlled blocking fixture chosen by the owner. Verify the device appears
   separately in Pi-hole's Query Log. A router acting as a DNS proxy can hide
   device identities. Encrypted DNS, VPNs and device policies can bypass Pi-hole.
5. In Pi-hole's Group Management UI, create only the profiles needed: a basic
   personal-device group and a smart-device group are enough to start. Assign
   clients and lists explicitly, review inherited Default membership, then test
   an allowlist exception on only the intended group. Start with conservative
   lists. DNS groups are filtering rules, not network isolation or user accounts.
6. Expand client DNS only after the outage/return drill and continuity policy in
   [home security](home-security.md) pass. A public secondary DNS server may
   bypass filtering; it is not transparent filtered failover. Do not move DHCP
   to the Pi just to get started.

Rollback: restore the saved client/router DNS settings first, verify internet
access, then troubleshoot the Pi through the independent management connection.
Keep the Pi's admin backends private throughout.

## Guests and smart devices

Enable the router's password-protected guest network only in a planned owner-run
change, preserving the primary Wi-Fi settings. Test from a guest device that
internet access works and primary devices and Pi admin pages cannot be reached.
Repeat the relevant IPv4/IPv6 paths; an SSID name alone proves nothing.

The [CR1000A guide](https://www.verizon.com/supportresources/content/dam/verizon/support/consumer/documents/internet/verizon-router_user-guide.pdf)
describes guest/primary firewall separation, but its IoT SSID lets IoT and primary
devices communicate. Do not treat that IoT label as isolation or assume this is
the owner's router model. Smart devices may need explicit local connections for
casting or automation; test intended access rather than opening the whole LAN.

Guest DNS filtering remains optional and NEEDS_CONFIGURATION until the actual
router can allow just TCP/UDP53 to the Pi, preserve individual client identities,
and deny all other unintended primary-network access. If it cannot, retain guest
isolation and the router's guest DNS. Do not disable isolation to get a query log.
Pi-hole shows DNS requests it receives, not bandwidth totals or encrypted content.
Per-device traffic reporting and a whole-home VPN require suitable gateway
features; neither is implemented by this guide.

## Use Pi-hole while away

This is optional DNS over Tailscale on selected personal devices. It does not
change their browser egress, advertise an exit node, or route the home subnet.
Keep the Pi's `--accept-dns=false` setting to avoid a resolver loop.

1. First verify Tailscale enrollment, private access and recovery using
   [access](access.md). Save the current tailnet DNS/policy and Pi-hole settings.
2. Adapt [the DNS grant example](../config/tailscale-dns-policy.example.json)
   into the existing policy for the chosen personal identities. It is a policy
   fragment, not a replacement file. Preserve management grants, review broad
   pre-existing rules, and test allowed and denied identities. Authorize both
   TCP and UDP53 to the Pi; keep admin access separate.
3. Pi-hole's default `local` mode can reject remote tailnet clients. Before using
   `all`, review the actual host/router IPv4 and IPv6 firewall: allow DNS only
   from intended LAN clients and authorized tailnet clients, deny WAN and other
   unintended paths, and verify there is no port53 forward. This guide installs
   no firewall rules. Implement and test the actual policy with the recovery
   connection available; unknown boundaries remain pending.
4. Only after that review, privately set `PIHOLE_LISTENING_MODE=all` and
   `ACK_REMOTE_DNS=yes` in `.env`. Managed validation refuses an unacknowledged
   `all` mode. The acknowledgment is not evidence of a working firewall. Apply
   only Pi-hole through the [backed-up scoped update](updates.md) procedure at
   the exact reviewed revision, preserving project, mounts and the admin listener.
5. From one allowed personal device away from home, test UDP and TCP queries to
   the Pi's actual Tailscale address and the chosen blocking fixture. Verify that
   a denied tailnet identity cannot resolve through it and direct WAN access is
   denied. Repeat IPv6 where applicable. Keep test results private.
6. Follow [Tailscale's Pi-hole guide](https://tailscale.com/docs/solutions/block-ads-all-devices-anywhere-using-raspberry-pi)
   to add the Pi's Tailscale address as a nameserver. Review which devices will
   accept an Override DNS change before enabling it; it can affect the whole
   tailnet, including work devices. A DNS grant does not select which clients
   receive the nameserver setting. Test a manual resolver setting on one personal
   client first. Before enabling a tailnet-wide override, use each excluded
   client's supported DNS preference to retain its existing resolver (for CLI
   clients, `tailscale set --accept-dns=false`); keep the Pi's setting unchanged.
   Follow [Tailscale DNS settings](https://tailscale.com/docs/reference/dns-in-tailscale)
   for the actual client platforms. Verify normal browsing, blocking, reconnection, and
   behavior when the Pi or home internet is unavailable.

Rollback: restore the saved tailnet DNS settings so clients can resolve without
the Pi, restore the previous narrow DNS grant, then set the Pi back to `local`
and `ACK_REMOTE_DNS=no` through a scoped Pi-hole recreation. Verify original LAN
DNS and remote management still work. Do not reset Serve or Tailscale state.

## Know when something breaks

Use [operations](operations.md#register-native-monitors-and-notifications) to
enroll Kuma. Start with a functional DNS monitor, an internet HTTPS endpoint
chosen by the owner, and one private service. Check the path from the Kuma
container: its loopback is not the Pi host. Test one authorized failure and
recovery notification before claiming alerts work.

If speed history is useful, review `./pi plan --enable diagnostics`, then follow
the [diagnostics module](../modules/diagnostics/README.md) enablement and account
setup. Keep its existing six-hour schedule to start; record that wired Pi tests
measure its own ISP/egress path, not guest-device bandwidth or Wi-Fi coverage.
Netdata reports Pi/container resources, not all household traffic. Do not add
frequent tests before checking actual DNS latency and Pi capacity.

An observer on this Pi cannot report its own full failure. Choose and test an
off-Pi observer before claiming power/home-internet outage alerts. Backups,
freshness checks and disk review remain in [operations](operations.md); no new
alert framework is needed.

## Completion evidence

Record the router model, named devices, original settings, allowed exceptions,
DNS coverage, guest boundary tests, remote-DNS client tests, monitor enrollment,
notification receipt and recovery results in ignored `local/`. Update the related
[TODO items](TODO.md) only after these checks actually run. A Compose model or
matching listener does not establish network safety.

References: [Pi-hole client groups](https://docs.pi-hole.net/group_management/example/)
and [FTL listening modes](https://docs.pi-hole.net/ftldns/configfile/#listeningmode).
