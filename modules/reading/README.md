# Reading

FreshRSS stores subscriptions, articles, read/starred state, account configuration and SQLite databases under `freshrss/data`. Installed extensions live under `freshrss/extensions`; both directories are essential backup state. This module is opt-in and runs independently of DNS and the browser VPN.

Run `./pi plan --enable reading`, review the new state paths, fetch the pinned image with `./pi pull reading`, then run `./pi enable reading`. For an existing installation, inventory and back up its data before adopting these paths. Keep the initial setup private: from your computer, open `ssh -N -L 8082:127.0.0.1:8082 USER@PI`, then visit `http://127.0.0.1:8082`. Complete the web wizard, choose SQLite and form authentication, create your own account and strong password, and keep anonymous access and APIs disabled. Remove any bundled example subscriptions you do not want. This repository adds no subscriptions. No account password belongs in Compose or the root `.env`.

Doctor checks HTTP liveness, which also succeeds while the setup wizard is available. Authentication, retention confirmation and route enrollment remain `NEEDS_CONFIGURATION` until you have checked them. Follow [private access](../../docs/access.md) to enroll the application after proving anonymous clients cannot read it. Its private HTTPS port is `8450`, forwarded to host loopback `8082`. Set FreshRSS's base URL to the actual private HTTPS address when enrolling it; never guess a tailnet name. Test an allowed device, a denied device, and a signed-out browser.

In your user's **Configuration → Archiving**, confirm the retention settings. The pinned 1.30.0 release defaults to three months, a maximum of 200 and minimum of 50 articles per feed, while retaining favourites and labelled articles. Those exceptions can grow indefinitely; this is a bounded ordinary history policy, not a disk quota. Per-feed overrides may change it. Keep saved items intentionally, review disk use, and shorten ordinary history when needed. Do not rely on the legacy CLI `--purge-after-months` option to describe the current `archiving` settings. [Release defaults](https://github.com/FreshRSS/FreshRSS/blob/1.30.0/config-user.default.php)

Feed refresh runs at minutes `17,47` each hour in `TZ`; change `FRESHRSS_CRON_MIN` in the root `.env` to adjust it. FreshRSS also respects each feed's refresh interval. A manual refresh for an existing user uses the supported CLI and does not require a password:

```sh
docker exec --user www-data freshrss cli/actualize-user.php --user YOUR_USERNAME
```

Export subscriptions to an OPML file, using a private directory and an output filename that does not already exist:

```sh
umask 077
set -C
docker exec --user www-data freshrss cli/export-opml-for-user.php --user YOUR_USERNAME > local/subscriptions.opml
```

OPML includes feed URLs and folder structure. It does not replace the SQLite backup and does not contain read/starred history. Subscription URLs themselves can contain private tokens. Use the web **Import / export** page to import your own OPML. [Supported CLI](https://github.com/FreshRSS/FreshRSS/tree/1.30.0/cli)

Run `./pi backup reading` with the configured off-device encrypted repository. The stop adapter pauses only FreshRSS long enough to archive both mounts and resumes it before upload. Restore an exact snapshot into a fresh quarantine directory with `./pi restore SNAPSHOT_ID TARGET`; retain the numeric ownership from its archives, test a separate container with restored state, and verify accounts, subscriptions, articles, read/starred state and extensions before any cutover. Never start a second instance against the live SQLite directory. `./pi disable reading` preserves both directories; re-enabling uses the same paths. Image upgrades can migrate state, so rollback may require restoring the matching pre-upgrade data as well as the previous image. See [recovery](../../docs/recovery.md).

The image follows [FreshRSS's Docker documentation](https://github.com/FreshRSS/FreshRSS/blob/1.30.0/Docker/README.md). It sets the Debian `www-data` group permissions it needs; retain numeric owners/modes during restore instead of applying a guessed host UID.
