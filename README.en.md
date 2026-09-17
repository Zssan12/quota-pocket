# Quota Pocket

**AI API balances and ChatGPT / Claude quotas on your iPhone Home Screen.**

[简体中文](README.md) · English

```text
Mac / Windows collector → your iCloud Drive → iPhone Scriptable widget
```

Credentials stay on your computer. No server, domain or VPN pairing required. Quota Pocket queries allowances, not conversations or model inference.

## Features

- API balances from CC Switch's configured usage scripts, in their original currencies.
- Multiple ChatGPT / Claude accounts, remaining allowances and reset times.
- Small, medium and large widgets with account selection, ordering, group rotation and quota colors.
- Offline snapshots with original collection timestamps; unknown never means zero.

## Get started

Install [Python 3.9+](https://www.python.org/downloads/), [Node.js 20+](https://nodejs.org/) and [Scriptable](https://scriptable.app/) on iPhone. Enable iCloud Drive on both devices with the same Apple Account. Windows also needs iCloud for Windows.

### Mac

For a fresh installation from current source:

```sh
git clone https://github.com/Zssan12/quota-pocket.git
cd quota-pocket
bash install.sh --source "$PWD"
```

The local setup page opens automatically. You can close the terminal after installation. After restarting your Mac, open `Start Quota Pocket.command` in `~/Library/Application Support/QuotaPocket`.

This command does not upgrade an existing installation. See [Mac operations and upgrades (Chinese)](MAC.md).

### Windows preview

```powershell
git clone https://github.com/Zssan12/quota-pocket.git
cd quota-pocket
npm ci --ignore-scripts
.\start-windows.cmd
```

Keep the collector window open. See the [Windows guide (Chinese)](WINDOWS.md) for updates, custom iCloud paths and proxy support.

Without Git, [download the ZIP](https://github.com/Zssan12/quota-pocket/archive/refs/heads/main.zip), extract it and run the corresponding installation command inside the project. Or [ask a local AI assistant to install it](AGENT-INSTALL.en.md).

## Connect your iPhone

1. Connect an account on the computer and confirm a successful quota query. Subscription authorization requires the corresponding Codex / Claude CLI.
2. Open Scriptable on iPhone once and enable iCloud access.
3. Enable iCloud in the computer's widget setup page and note the generated script name.
4. Run that script on iPhone, choose accounts, then add a Scriptable Home Screen widget pointing to it.

## Limits

- A sleeping or powered-off computer cannot collect new data. The default five-minute collection interval is **not a guaranteed widget refresh interval**.
- Apple controls iCloud delivery and widget refresh. Running the script rereads available data; it cannot force cloud delivery. Rotation also depends on iOS scheduling.
- Windows file transport and a real relay balance query have been tested. Subscription login, automatic startup and the latest full phone workflow still need device validation.
- For Clash/Mihomo Fake-IP errors, explicitly enable Fake-IP compatibility under CC Switch independent queries. It is off by default.

## More

[Mac operations](MAC.md) · [Windows guide](WINDOWS.md) · [Connectivity](CONNECTIVITY.md) · [Validation](VALIDATION.md)

Run `npm ci --ignore-scripts` and `npm test` before contributing. Reports should include OS versions, steps and redacted errors. Never upload `.state`, keys or account snapshots. The app UI is currently in Chinese.

[MIT](LICENSE). Thanks to [Scriptable](https://scriptable.app/), [CC Switch](https://github.com/farion1231/cc-switch) and [CodexBar](https://github.com/steipete/CodexBar). Independent project, not affiliated with the providers.
