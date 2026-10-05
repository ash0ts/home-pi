# Adding a service

Add a module only for a concrete household use. Start from `modules/_template`; its unresolved image placeholder prevents accidental deployment. A module consists of one authoritative `compose.yaml`, small `module.json`, secret-free environment examples, and an operating note. Adding a service does not require editing the installer or command dispatcher.

Compose owns runtime images, mounts, ports, networks, environment names, health checks, logging, and resource settings. Metadata owns module dependencies, HTTPS route intent, required secret names, and backup classification of writable container paths. Do not duplicate backend ports, bind sources, volume names, or image versions in metadata. `schemas/module.schema.json` describes the file shape; the standard-library validator also checks cross-file relationships.

1. Choose and verify an upstream ARM64 release and immutable image digest. Document image-specific health probes and authentication. Keep optional services off host networking and use a dedicated network.
2. Publish an explicit loopback backend. `ADMIN_BIND_IP` permits a specific RFC1918 address only with `ACK_LAN_ADMIN=yes`; this exception requires separate LAN/guest/IoT checks. Reserve a unique HTTPS port for private access and specify the application login requirement. `https+insecure` is reserved for a self-signed HTTPS backend on loopback; the Tailscale front end still uses valid HTTPS. A route is not an authorization policy by itself.
3. Put secret names in metadata and real values in private root `.env`. Never use `env_file` to pull arbitrary private files into the model. Disabled modules do not require their secrets.
4. Classify every writable mount as essential, history, or cache with stop consistency. Keep existing paths during extraction. Cache exclusions need a reason in the operations note. Relative paths resolve from the root project directory.
5. Record expected external data filesystems in private `local/storage.json`, for example `{"mounts":[{"path":"/mnt/home-pi"}]}`. Optional numeric `device` is the filesystem's `st_dev` identity. An absent mount aborts changes; the command never creates a directory to mask the missing disk.
6. Run isolated tests, then `./pi plan --enable MODULE`. The plan renders Compose read-only and prints explicit file ordering, selected services, route intent, storage mappings, and resource settings. It never prints service environments. `./pi enable MODULE --dry-run` only reads metadata and invokes no Docker commands.
7. Back up and test restoration before live enablement. `./pi enable MODULE` validates the complete candidate, checks required ports, starts only new services with `--no-deps`, and waits for doctor. If readiness fails it restores the selection and stops new services, retaining data. Route registration remains NEEDS_CONFIGURATION until the access layer is available and live allowed/denied checks pass.

`./pi disable MODULE` refuses an in-use dependency. It stops only removed services using the previous Compose file list, then updates selection. It does not remove containers, bind data, or named volumes. Re-enabling uses that retained state. Rollback after an application schema migration still requires matching data restoration, not only a previous image.

New installations explicitly choose `./pi init --preset standard` (core plus health) or `--preset core`. Existing installations use `./pi init --existing` to import deployed service labels and preserve previously enabled functionality; unknown services block import for review. Never infer a migration from the new-install preset.

Use `./pi backup MODULE` for selected module data, `./pi doctor --services SERVICE` for runtime checks, and `./pi status` for redacted status. The shared catalog feeds backup, doctor and private access planning; dashboard links and monitors use native settings. Service-specific code belongs only where an upstream protocol requires it. Runtime changes do not restart core DNS or Tailscale.

For regression checks like the home/files modules, reuse `tests/module_fixture.py`
for dummy Compose models and fake lifecycle commands. Keep upstream runtime
smoke checks isolated from household devices and identities; they establish only
their recorded scope.

Prove feed refresh and read/star state restoration for the reading module before relying on it. Hardware-dependent modules and actual network isolation remain pending until their devices and clients exist. Static validation is not live deployment evidence.
