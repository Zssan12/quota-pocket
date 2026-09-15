# Install with a local agent

[简体中文](AGENT-INSTALL.md) · **English**

Copy the prompt below into a local agent that can operate your Mac, such as Codex, Claude Code, or WorkBuddy. A web chat without local access cannot perform the installation for you. The prompt uses this project’s repository. If you already downloaded the source, replace the project URL with its absolute local directory path.

```text
Please install and start Quota Pocket on this Mac, through to opening its local configuration page.

Project: https://github.com/Zssan12/quota-pocket
Version: v0.2.0 preview. If the tag does not exist, tell me and let me choose an available version. Do not invent a repository address.

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

Do not paste account secrets into this prompt. Complete authorization in the project's local management page.
