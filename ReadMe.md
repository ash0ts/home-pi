# Home Pi

A few useful home services, together on a Raspberry Pi: ad filtering, private remote access and a home page for your apps.

## What you get

New installations start with four services:

| App | What it does |
| --- | --- |
| **Pi-hole** | Helps block ads and trackers on devices set up to use it. |
| **Tailscale** | Gives you private remote access to your Pi. |
| **Homer** | Puts links to your apps on a simple home page. |
| **Uptime Kuma** | Checks whether the services you choose are up. |

Add other apps when you need them: **FreshRSS** for following blogs and news, a **Webtop browser with its own VPN**, or tools for speed tests, system stats and container management. These extras stay off until you choose them.

Want to make the house more useful? Add [Home Assistant](modules/home/README.md)
for one compatible device and a simple automation. It stays off until selected.

Ad filtering, remote access and the browser VPN each do a different job. The browser VPN applies to that browser; it doesn’t put your whole home behind a VPN.

## Start here

- **Setting up a new Pi?** Follow the [setup guide](docs/setup.md).
- **Already running Home Pi?** Start with [existing installations](docs/setup.md#existing-installations) to keep your settings and data.
- **Picking up where we left off?** Open the [remaining-work checklist](docs/TODO.md). It starts with finding the Pi and confirming how to connect—no need to know the technical details beforehand.

The code and automated checks are in place. Checks on the actual Pi and home network are still pending; [delivery notes](docs/implementation-status.md) record what has been tested.

## Find what you need

| I want to… | Guide |
| --- | --- |
| Open my apps privately | [Access and sign-in](docs/access.md) |
| See what’s working or troubleshoot a problem | [Diagnostics](docs/diagnostics.md) |
| Back up or recover my data | [Backup and recovery](docs/recovery.md) |
| Update the apps | [Reviewed updates](docs/updates.md) |
| Set up dashboard links, monitoring and schedules | [Everyday operations](docs/operations.md) |
| Organize devices, guest Wi-Fi and DNS filtering at home or away | [Start with your network](docs/network.md) |
| Try the feed reader or private browser | [Reading](modules/reading/README.md) · [Browser](modules/browser/README.md) |

Working on the repository? Start with the [agent skill](.agents/skills/home-pi/SKILL.md) and [contributor rules](AGENTS.md). The [module guide](docs/adding-a-service.md) explains how to add a service.
