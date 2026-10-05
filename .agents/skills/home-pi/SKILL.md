---
name: home-pi
description: Maintain, troubleshoot, or resume work in the home-pi repository using its Compose modules, maintenance commands, runbooks and deployment evidence. Use for home-pi changes and operational handoffs, not unrelated Raspberry Pi projects.
---

# Work on home-pi

Keep this a small Compose deployment with a thin command layer. Prefer an existing command, native application setting or short runbook over another abstraction. Add automation only for a concrete repeated need; the owner explicitly asked to keep this project lean.

## Establish the current task

Read [AGENTS.md](../../../AGENTS.md), [remaining work](../../../docs/TODO.md) and [delivery evidence](../../../docs/implementation-status.md). Resolve these paths from this skill's directory. Check the working tree, current branch and PR status before editing. Do not replay the original implementation plan or append work to its merged stack.

For a resume request, identify the first unchecked item with available inputs and authorization. Treat a narrower user request as the scope; do not turn a small fix into a full infrastructure audit. Missing Pi access does not block independent repository work. Ask for the specific missing target or decision when it blocks the next live step; do not infer a host from credentials or unrelated local containers.

If the owner does not know the connection details, explain them as the device address and login name and guide the discovery step in `docs/TODO.md`. Do not keep asking for an unexplained “SSH target” or assume a default account.

Repository edits, PRs and CI establish code behavior. They do not establish live deployment or authorize router/firewall/VPN changes, service interruption or notifications. Carry forward explicit authorization already given for the same operation; do not ask again merely because the session resumed. Follow AGENTS.md for secret handling and state preservation.

## Choose the existing path

| Work | Read or use |
| --- | --- |
| Configure/start/diagnose | `./pi --help`, `scripts/setup.py`, `scripts/doctor.py`, [diagnostics](../../../docs/diagnostics.md) |
| Add/change an optional service | [module contract](../../../docs/adding-a-service.md), `modules/<id>/compose.yaml` and `module.json` |
| Private routes or app enrollment | [access](../../../docs/access.md); route registration and application login are separate checks |
| Data recovery or image change | [recovery](../../../docs/recovery.md), [updates](../../../docs/updates.md), `config/images.lock.json` |
| Actual host/client checks | [home security](../../../docs/home-security.md); keep observations in ignored private `local/` |
| Homer, monitors, schedules or capacity | [operations](../../../docs/operations.md); use native settings first |
| Browser namespace or legacy migration | [browser VPN](../../../docs/browser-vpn.md); Gluetun/Webtop form one lifecycle unit |

Read only the relevant runbook and source, then make the smallest complete change. Do not copy a service into a second Compose definition, add installer branches for modules, or make automatic monitor/portal generation a prerequisite for an unrelated fix. Preserve the distinction between DNS, private access and browser egress.

## Deliver and leave a usable handoff

Use one PR for one concern. Create dependent layers only when they improve review; start new follow-ups from the verified target branch after the prior stack has merged. When editing an active stack, fix the owning layer and rebase its dependents using the available stack workflow. Do not rename an existing branch unless asked. Open or merge PRs within the user's requested scope; a new-PR request alone is not a request to merge it.

Run the applicable checks required by AGENTS.md. For documentation/skill-only work, validate the skill frontmatter and local links; avoid adding runtime tests for prose. For code or Compose changes, use the existing fixture tests and static validator. Use dummy inputs; a production restart is not a test. Report skipped prerequisites and what each check actually establishes.

Update `docs/TODO.md` when a remaining item changes. Keep historical delivery evidence separate from current live observations. A completion note should say what changed, the exact revision/PR, checks and limits, and the next action or missing input. Do not mark live gates complete from CI, synthetic fixtures or a container healthcheck. Keep raw/private evidence out of the PR and never rely on this workspace's `.context/` attachments being available to the next agent.
