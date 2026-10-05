# Keep a few personal folders in sync

Use Syncthing for a selected folder on a personal computer and the Pi: project
exports, chord sheets or documents are good starting points. Pair devices
explicitly and approve each shared folder. This module does not select folders,
pair computers or promise mobile-client support automatically.

Sync copies changes and deletions. Independent backups remain necessary.

## Prepare and enable

Complete the baseline [TODO](../../docs/TODO.md), [off-device recovery](../../docs/recovery.md)
and [capacity review](../../docs/operations.md#retention-and-capacity) before live
use. Existing Syncthing installations need an inventory of their device identity,
configuration, folder IDs, paths, index format and ownership before migration.
Do not replace certificates or rename existing folders to match an example.

Create a new private `syncthing` directory only if absent, owned by the existing
non-root PUID/PGID (`install -d -m 0700 syncthing` as that owner on Debian). The
service runs directly as that user and cannot repair ownership automatically.
Existing ownership mismatches are rejected; inspect and repair deliberately,
without recursive changes to an unrelated tree. Record actual external mounts
in `local/storage.json` when applicable.

```sh
./pi plan --enable files
./pi pull files
./pi enable files
./pi doctor --services syncthing
```

Only the optional service starts. Native self-upgrades are disabled so image
changes use the [reviewed update workflow](../../docs/updates.md). The upstream
healthcheck and doctor prove process/GUI liveness, not successful file sync.

## Private admin access

Open `ssh -N -L 8384:127.0.0.1:8384 USER@PI` from your personal computer using
the confirmed connection, then browse to `http://127.0.0.1:8384`. Choose a unique
GUI username/password in Settings > GUI before publishing a private route.
Keep the backend on HTTP8384; Tailscale supplies the browser-facing HTTPS.

Follow [access enrollment](../../docs/access.md#https-registration), preserving
existing entries and adding `syncthing` only after login works. Grant only the
chosen administrators TCP8452, apply its owned HTTPS route, test allowed/denied
clients and add the verified URL to Homer. GUI access and sync transport are
different permissions; an HTTPS route does not carry file synchronization.

## Choose the sync connection before pairing

No TCP/UDP22000 or UDP21027 host ports are published. Bridge networking does not
provide LAN multicast discovery. Pick one tested path:

- **Direct connection to a personal computer:** run an appropriate Syncthing
  client there and add its real LAN or Tailscale `tcp://ADDRESS:22000` endpoint
  to the device entry on the Pi. The Pi initiates the connection; the computer
  must accept it under its own firewall and, for Tailscale, explicit TCP22000
  permissions. Verify actual Docker/Tailscale forwarding. Keep the computer's
  GUI private. Once direct connectivity is proven, disable global discovery,
  local discovery, relays and NAT traversal in the Pi's native connection
  settings if they are unnecessary. Both devices must be online to sync.
- **Upstream discovery and relays:** the upstream defaults may contact public
  discovery/relay infrastructure when this module starts. Review those settings
  and accept that mode explicitly before sharing household files. Relay traffic
  is encrypted between paired devices, but endpoints/discovery have their own
  metadata/privacy implications. Confirm that the chosen path actually connects;
  do not treat a healthy GUI as proof.

Do not open router forwards or disable guest isolation to fix connectivity.
If neither path works, stop and record NEEDS_CONFIGURATION; incoming Pi sync
listeners require a separate reviewed network design. Do not expose data ports
by relaxing the shared admin-bind policy.

## Pair one computer and folder

1. Compare device IDs through a trusted channel and approve the exact personal
   devices in each native UI. Do not enable automatic folder acceptance.
2. On the Pi, choose a new path such as `/var/syncthing/files/first-folder`. It
   maps inside the private `syncthing` bind and is included in backups. Do not
   sync the whole home directory, `.env`, credentials, live app databases, Docker
   state or active build caches. Avoid paths outside this bind; the module has
   no implicit access to other household files.
3. Decide folder direction: Send & Receive for deliberate two-way editing,
   Receive Only for a Pi copy of computer-owned files, or Send Only for a
   Pi-owned source. Review what the selected mode does with local edits. Choose
   native versioning/retention according to the actual folder's size and needs.
4. Test a harmless text file, an edit, a deliberate conflict and deletion on
   each applicable side. Verify versions and independent backup recovery, then
   use native bandwidth limits if needed. Measure indexing/transfer impact on
   Pi DNS latency, memory and disk before sharing larger folders.

## Backup, restore and disable

The entire `/var/syncthing` bind is essential stop-consistent state: device
certificates, GUI credentials/API key, configuration/indexes, synced files and
versions. This also covers the upstream image's declared volume; no untracked
anonymous data volume is expected. `./pi backup files` includes that bind, but
does not back up unrelated folders on the computer. Check both sides' recovery
needs separately. No version/cache exclusion is assumed; review disk growth.

Restore the matching image/data into quarantine using [recovery](../../docs/recovery.md).
Before any restored startup, isolate it from peers and public discovery/relays:
the restored certificate is the same device identity. Never run it alongside
the original on a reachable network. Verify login, folder/index paths and files
on the isolated target. Recover a mistakenly deleted file from the independent
backup into a separate review folder; reintroduce it only after deciding which
peer/mode should own it. An older binary alone is not an index/data rollback.

`./pi disable files` removes the owned GUI route and stops only Syncthing; data
and identity remain for re-enable. Record effects on other peers. Check that
core DNS/Tailscale container IDs remain unchanged.

## Live acceptance

- [ ] Private GUI login and denied-client behavior verified.
- [ ] Exact personal device and folder paired over the chosen transport.
- [ ] Edits, conflicts, deletions and selected folder mode understood.
- [ ] Independent backup restores a deleted file and the isolated app identity.
- [ ] Transfer/indexing stays within measured DNS/RAM/disk limits.
- [ ] Restart and disable/re-enable retain state and leave core IDs unchanged.

These checks are NOT RUN on the household setup. Keep dated observations in
ignored `local/` and update [TODO](../../docs/TODO.md) when they exist.

Sources: [upstream Docker image](https://github.com/syncthing/syncthing/blob/v2.1.5/README-Docker.md),
[configuration](https://docs.syncthing.net/users/config.html),
[command options](https://docs.syncthing.net/users/syncthing.html),
[relay security](https://docs.syncthing.net/users/relaying.html), and
[backup limitations](https://docs.syncthing.net/users/faq.html#is-syncthing-my-ideal-backup-application).
