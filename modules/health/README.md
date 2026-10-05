# Health

Opt in with `./pi plan --enable health` and `./pi enable health` after inventory, backup and access review.

Existing mount paths and volume names are retained. Use the private HTTPS route described in [access](../../docs/access.md); complete first-run authentication through a loopback SSH tunnel before publishing its route.

`./pi disable health` stops only owned services and preserves data. Re-enable the same pinned images; review image/data migrations separately. `./pi backup health` captures classified state with the stop adapter; use a fresh quarantined restore target and verify actual app settings/history before cutover.

Monitor registration and allowed/denied client tests remain pending until performed. See [recovery](../../docs/recovery.md) and [diagnostics](../../docs/diagnostics.md).
