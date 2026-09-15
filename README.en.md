<div align="center">

# Quota Pocket

**AI account quotas on your iPhone Home Screen. Credentials stay on your Mac.**

[简体中文](README.md) · **English**

macOS · iCloud Drive · iPhone Scriptable · MIT

</div>

Quota Pocket is an open-source quota viewer for AI accounts. A Mac collects provider balances and subscription limits, then syncs a filtered snapshot through your own iCloud Drive to a Scriptable widget on your iPhone. No server deployment or connection from your phone to your Mac's network address is required.

## Features

- **Multiple quota sources:** CC Switch provider queries, ChatGPT / Codex subscriptions, Claude subscriptions, and CodexBar.
- **Home Screen widgets:** small, medium, and large widgets show groups of 1, 2, and 4 accounts. Additional accounts rotate in groups. Subscription windows include reset times.
- **Guided setup:** the installer opens a local page with four steps: connect an account, confirm a successful query, sync to iCloud, and add the iPhone widget.
- **Honest status:** failed queries and offline reads retain the last successful data and its original timestamp. Unknown quotas are not shown as zero, and a passed reset time does not imply a full quota.

```text
Mac collector → allowlisted quota snapshot → your iCloud Drive → iPhone Scriptable
```

API keys, OAuth tokens, and login credentials stay on your Mac. iCloud snapshots contain only allowlisted display fields, and the iPhone does not need account credentials. Quota Pocket reads quota information; it does not read conversations, estimate spending, or send inference requests.

> v0.1.3 is an early preview. The core collection and iCloud path has been tested; background permissions and different iPhone system states still need real-device validation. The configuration UI and widget are currently in Chinese. This language switch applies to the documentation.

## Installation

You need macOS, Python 3.9+, and Node.js 20+ with npm. Your Mac and iPhone must use the same Apple Account with iCloud Drive enabled.

<a id="agent-install"></a>

**Prefer help from a local agent?** Copy the prompt below into Codex, Claude Code, WorkBuddy, or another local agent that can operate your Mac. It can check dependencies, install the project, and open setup. You complete account authorization and iPhone actions yourself.

<details open>
<summary>Installation prompt (copy directly, or click to collapse)</summary>

```text
Please install and start Quota Pocket on this Mac, through to opening its local configuration page.

Project: https://github.com/Zssan12/quota-pocket
Version: v0.1.3 preview. If the tag does not exist, tell me and let me choose an available version. Do not invent a repository address.

Quota Pocket collects AI account quotas on a Mac, writes an allowlisted snapshot to my own iCloud Drive, and displays it in an iPhone Scriptable widget. Credentials stay on the Mac.

Please carry out these steps, rather than just giving instructions:
1. Read README.en.md and install.sh / install.py. Follow the project's and this session's operating constraints.
2. Check macOS, Python 3.9+, Node.js 20+, and npm. Reuse working tools. If tools are missing and Homebrew is installed, install only the missing tools. If Homebrew is absent, provide official installer links and explain the step I need to perform. Do not use sudo or modify Apple's system Python.
3. Download the selected version into a separate directory, or use the local source directory I provided. Do not initialize or modify Git in an unrelated project. Do not delete or overwrite my existing source or account state.
4. From the source directory, run: bash install.sh --source "$PWD"
   It installs to ~/Library/Application Support/QuotaPocket and preserves accounts and the installation ID of an existing installation. Never delete .state to reinstall. This entry point does not upgrade an existing installation.
5. Verify that the local service started and setup opened. If the port is occupied, identify the listener before acting; do not force-kill it. Do not put API keys, tokens, authenticated URLs, or real account information into chat or logs.
6. Ask which quota source I want. When account authorization is needed, let me complete it in the local page. Do not enable every source automatically or read conversations. Check Codex CLI or Claude CLI only if the selected source requires it.
7. Guide me through a successful quota query, enabling iCloud, running the dedicated script in Scriptable, and adding the Home Screen widget. Both devices must use the same Apple Account with iCloud Drive enabled. I perform the phone actions. Do not equate a Mac write with confirmed phone delivery.
8. Use the installer-started process first. Automatic login startup is experimental; configure it only if I want it and verify macOS file permissions. Do not expose a public endpoint or deploy a sync server.

Finish with the install location, startup result, how to reopen it, and my next page or phone action. Do not delete files or directories for cleanup.
```

</details>

Do not paste keys or login credentials into the prompt. Complete account authorization in the local setup page.

### One-line install

Paste this command into Terminal on your Mac:

```sh
curl -fsSL https://raw.githubusercontent.com/Zssan12/quota-pocket/v0.1.3/install.sh | bash -s -- --repo Zssan12/quota-pocket
```

The installer checks your environment, downloads the specified version, installs the query dependencies, starts the local service, and opens setup in your browser. Source code comes from that GitHub repository. npm uses the lockfile with install scripts disabled. The installer does not install system tools, enable login startup, or require sudo.

If Python or Node.js is missing, it explains what to install. With Homebrew already installed, run `brew install python node`. Alternatively, use the official [Python](https://www.python.org/downloads/macos/) and [Node.js](https://nodejs.org/en/download) installers. Open a new terminal afterward and retry the installation command.

### From downloaded source

Use Code → Download ZIP on GitHub and extract it, or clone the repository. In the directory containing `install.sh`, run:

```sh
bash install.sh --source "$PWD"
```

Both methods install to `~/Library/Application Support/QuotaPocket`. Running the installer again opens the existing installation and preserves accounts and the installation ID; **it does not upgrade an existing installation**. You can close the terminal after successful installation. After restarting your Mac, rerun the command or double-click `Start Quota Pocket.command` in the installation directory.

Downloaded files and dependency preparation bundles remain in `.installer`. Do not publish your installed runtime directory as source code.

### Connect your iPhone

1. Install and open Scriptable on your iPhone, and allow iCloud access.
2. On the Mac page, choose “一步步配置” (guided setup): connect an account → confirm its quota → sync to iCloud → add the phone widget. Existing progress is detected; advanced settings are collapsed.
3. Enable iCloud sync. After a successful write, the page shows the dedicated script name.
4. Wait for that script to appear in Scriptable on your iPhone and run it once. Add a Scriptable widget to the Home Screen, edit it, and select the same script.
5. Confirm that the widget shows your quota. Automatic startup at login is optional.

The management service listens only on `127.0.0.1:8931`. The installer opens a locally authenticated page and reuses an already running service. Opening the bare address without management credentials will not reveal account counts or the collection interval.

## Background operation and updates

**Automatic startup at login is experimental.** macOS may deny background Python access to iCloud or source files. Login startup after granting these permissions has not completed real-device validation. Start with the installer workflow. If login startup encounters permission errors, run `python3 service_manager.py disable` in the installation directory, then rerun the installer to restore collection.

From the installation directory:

```sh
python3 service_manager.py start
python3 service_manager.py status
python3 service_manager.py restart
python3 service_manager.py disable
```

`start` and `restart` enable login startup through launchd. `disable` (also called `stop`) stops collection and disables future login startup while keeping accounts, settings, logs, and iCloud files. You can also run `python3 server.py --open` manually; keep that terminal running.

The management page shows the running version and build identity. Its restart button restarts the installed copy. The installer supports first installation and reopening; there is no self-service update workflow yet. Developers whose runtime was installed through the service manager from the same checkout can run `python3 service_manager.py restart` in that checkout to update it. This also enables login startup and requires permission validation.

A lock prevents concurrent collectors from writing to the same state directory. When login startup is enabled, launchd can restart the process; an installer-started process must be reopened if it exits. Collection pauses while the Mac sleeps and resumes when it can after waking. The default interval is five minutes, existing custom intervals are retained, and failures back off while keeping the last successful data.

Runtime code and account state live in `~/Library/Application Support/QuotaPocket`. Service-manager migration preserves the original source and state files, migrates account state once, and retains the installation ID. Later service-manager updates replace code without overwriting active account state. Custom ports and state directories are managed from the terminal.

launchd does not load shell configuration. Node, Codex, and Claude executables must be on PATH when login startup is installed. Use the isolated login flow for provider credentials instead of temporary shell variables. Background errors are logged at `~/Library/Logs/QuotaPocket/collector-error.log`; service-action errors are in `.state/service-action.log` inside the runtime directory. Collection logs retain roughly the latest 1 MiB after exceeding 2 MiB. Do not run Quota Pocket with sudo.

## Data sources

| Source | Quota information | Requirements |
| --- | --- | --- |
| CC Switch independent queries | Provider balances and plan quotas with query scripts enabled | Local CC Switch database and Node query dependencies |
| ChatGPT subscription | Codex quota windows and reset times | Isolated authorization from the setup page; Codex CLI required |
| Claude subscription | Five-hour, weekly, and model-specific limits | Isolated authorization; Claude CLI required; a regular API key is insufficient |
| CodexBar | Quota information returned by its CLI | Install and configure its CLI, then enable the source |

Subscription login uses isolated directories and does not change your existing tool accounts. Independent CC Switch queries make additional provider requests; enabling polling in both tools duplicates those requests. Cache reading is an experimental compatibility option requiring an export patch in the upstream tool.

Some providers are incompatible with the current read-only query constraints: HTTPS, same-origin GET requests, and no redirects. Unknown values remain unknown. Balances retain their original currencies and are not summed across currencies.

If you explicitly use a Fake-IP proxy, set `QUOTA_POCKET_FAKE_IP=1` when first launching or installing login startup. This permits domain resolution to synthetic proxy addresses, not localhost, literal IP addresses, or other private addresses. It is disabled by default. Preserve the setting in the environment when restarting a background service that needs it.

## Widget selection, rotation, and diagnostics

Run the script on your phone and choose “调整展示账户” (choose display accounts) to select and order accounts. Small, medium, and large widgets display 1, 2, and 4 accounts per group. Each displayed subscription window includes its reset time. Missing times are labeled explicitly; elapsed times await confirmation. Preferences stay on the phone and are not overwritten by Mac snapshots.

Rotation uses 15-minute time slots and the selected account order after filtering. The final group may have empty cells, and the header indicates the current group. **A group changes only when iOS runs the script again.** The Home Screen may stay on a group longer or skip a group if execution is delayed. Running again within the same slot shows the same group.

The Mac's advanced account scope controls which accounts may sync. Revocation takes effect after the phone receives the new snapshot; an offline phone may retain older cached data. Widgets for the same Mac installation share phone selection. The `codex` and `claude` widget parameters can filter the display.

“同步诊断 / 重新读取” (sync diagnostics / reread) reports the read source, failure stage, snapshot creation time, Mac collection completion time, and per-account successful query times. Rereading only checks data available on the phone. It cannot force Apple to sync, wake the Mac, or trigger an upstream query.

Failed queries retain old values and mark failure. Reading a cache does not change the underlying collection time. If the iCloud copy is older than the phone's cache, the newer cache is used. A reset time in the past does not imply that the quota has returned to 100%.

**A successful Mac write does not prove iPhone delivery.** Apple controls iCloud transport and Home Screen refresh scheduling. End-to-end updates have been confirmed on a real iPhone, but five-minute desktop refresh is not guaranteed. Lock screen, Low Power Mode, network changes, and sleep/wake behavior still need individual validation.

## Testing

From the source directory:

```sh
npm ci --ignore-scripts
npm test
```

The suite covers Python collection, Scriptable contracts, guided setup, and the path from collection to an installed script. It includes upstream failures, field allowlisting, older snapshots, offline caches, and account-scope revocation. Mock iOS APIs cannot replace device rendering and scheduling tests. Test artifacts remain in `output/test-runs` and are excluded from Git.

## Scope

The supported product route is Mac collection, iCloud sync, and iPhone Scriptable. Some legacy protocol compatibility code remains in the repository but is outside this preview's supported workflow.

## Documentation and feedback

- [Local-agent installation prompt](#agent-install)
- [v0.1.3 release notes](RELEASE-NOTES.md#english)
- [Connection troubleshooting (Chinese)](CONNECTIVITY.md)
- [Widget refresh research (Chinese)](WIDGET-REFRESH-RESEARCH.md)
- [Validation record and limitations (Chinese)](VALIDATION.md)
- [Current plan (Chinese)](MAC-IPHONE-ICLOUD-PLAN.md)

Issues and pull requests are welcome. Include macOS / iOS versions, reproduction steps, and sanitized errors. Do not include API keys, tokens, authenticated management URLs, or real account snapshots. Run `npm test` before submitting code.

## License and acknowledgments

Released under the [MIT License](LICENSE). Thanks to [Scriptable](https://scriptable.app/), [CC Switch](https://github.com/farion1231/cc-switch), [CodexBar](https://github.com/steipete/CodexBar), and the open-source dependencies used by this project. Bundled third-party licenses are retained in their respective directories.

This is an independent community project, not an official product of the AI service providers it supports.
