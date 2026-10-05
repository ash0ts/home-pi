# Reviewed updates and recovery

An update applies a reviewed, committed checkout to explicitly selected running services. It does not check out a branch, choose a new release, change router/firewall/VPN policy, or infer that an image downgrade can safely read a newer database. Review release notes and the actual ARM64 manifest for every pinned release/digest change.

Before the first migration, retain the installed project/container inventory, previous source revision, bind paths, named-volume identities, image IDs/digests, and a tested recovery procedure. Do not substitute the candidate checkout revision for the code that was deployed. Keep old images until the recovery window closes; avoid prune commands. If the old source revision cannot be established, review and document that migration gap before using the managed updater.

Retire the exact project Watchtower explicitly. The command verifies both Compose ownership labels, records the container identity, disables its restart policy, stops only that container, and verifies it stayed stopped. Deleting Watchtower from YAML alone does not retire the running updater.

```bash
./pi update --retire-watchtower --dry-run
./pi update --retire-watchtower
```

Choose and review the candidate checkout yourself. The updater requires a full commit matching current HEAD and a clean code tree, including untracked code. Private ignored runtime files are expected. `--candidate` is an alias for `--revision`.

```bash
# Replace both values with actual reviewed full 40-character commit IDs.
./pi update --revision CANDIDATE_FULL_COMMIT --previous-revision INSTALLED_FULL_COMMIT \
  --module health --dry-run
./pi update --revision CANDIDATE_FULL_COMMIT --previous-revision INSTALLED_FULL_COMMIT \
  --module health
```

`--previous-revision` is required for services without a trusted private deployment marker. Later updates preserve a separate source revision and exact image identity for each service, so an optional-service update does not falsely relabel core services as updated. If a running image differs from the recorded deployment, reconcile the inventory first. The initial previous revision is owner-supplied evidence, not an automatic attestation of the old installation.

The update validates shell/Compose configuration, selected module metadata, access, application keys, ownership, and storage. All affected images require immutable `@sha256:` references. Mutable tags and local build directives are refused. It then inventories actual mounted state, creates and verifies an off-device encrypted snapshot of the exact scope, pulls selected images, rechecks the reviewed checkout plus private configuration/active secret contents and the rendered model, and recreates only those services with `--no-deps --force-recreate`. A local restic fixture cannot satisfy this update gate. Editing `.env`, the selection, or an active Compose secret during a long backup/pull aborts recreation; fingerprints stay in memory and never appear in records.

Core DNS/remote access/portal and optional services require separate operations. Use explicit `--services pihole`, for example, when changing one core service. A Pi-hole backup/update requires `--allow-dns-interruption` after arranging the household continuity procedure. Tailscale changes require an independently tested management session and local recovery access. The command does not reset Tailscale enrollment or identity.

Services sharing a network namespace are updated together: selecting either the browser or its VPN namespace includes both. This prevents a recreated VPN container from leaving a browser attached to an obsolete namespace. The expanded service scope is recorded. Stopped or missing selected containers are refused before backup/pull so the updater cannot silently start disabled applications. Deliberately reconcile or enable those services first.

Readiness has two checks: Compose waits for the selected containers and their defined health checks, then doctor probes the affected service scope. `--wait-seconds` defaults to 300 and permits 1–21600 for a documented long migration window. For major Uptime Kuma/database changes, read the release-specific migration guidance and allow the necessary time; an early timeout is a failure report, not a reason to kill a still-working migration blindly. Doctor retries for at most 300 additional seconds.

Private mode0600 records live in `local/update-history/`, `local/last-update.json`, and `local/current-deployment.json`. Each attempt records its phase, selected services, candidate source revision, known previous source revisions, actual old image identities, and the verified snapshot ID. Successful records are written only after scoped readiness and installed-image verification. They do not attest to off-host client flows or household security.

If an update fails:

1. Inspect the redacted phase and snapshot ID in `local/last-update.json`, then run scoped doctor. A pull failure may leave all old containers untouched; a recreation/readiness failure may leave some candidate containers active. Preserve this evidence and current data.
2. Check the application's migration state before intervening. The updater does not automatically stop the stack, downgrade an image, or overwrite live data.
3. If recovery is needed, deliberately stop only affected writers, retain a copy of their current state, and restore the recorded snapshot to a fresh isolated target using the recovery runbook. Verify the archived application data before substituting it into production.
4. Use the recorded previous revision and exact image IDs/digests with that matching restored data. Recheck project identity, volume/bind paths, permissions, and secrets. Apply service by service, then verify DNS/access/client behavior and return the normal continuity policy.

A restored old image over a migrated database is not a safe rollback procedure. Never use `down -v`, prune old rollback images automatically, or replace the entire stack to repair one optional service. A failed route or network check remains unresolved until the actual client tests pass.

`renovate.json` requests reviewable image/digest updates with automerge disabled; it does not install or authorize the Renovate GitHub App. Update `config/images.lock.json` alongside a pin after verifying the release and ARM64 manifest. CI checks those records against the registries, validates all module models using dummy values, runs tests and linters, and scans for secrets. Keep untrusted pull-request code off privileged personal-data runners.
