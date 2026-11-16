# Security policy

## Supported versions

Security fixes go into the latest release only. Please check that the problem is still present in the [latest release](https://github.com/Gertrud-Violett/FTA_Editor/releases/latest) before you report it.

The legacy desktop app in `desktop/` is not supported and gets no security fixes.

## Reporting a problem

Please do not open a public issue for a security problem.

Report it privately through GitHub: open the [Security tab](https://github.com/Gertrud-Violett/FTA_Editor/security) of this repository and choose **Report a vulnerability**, or go straight to the [private report form](https://github.com/Gertrud-Violett/FTA_Editor/security/advisories/new).

Include:

- the FTA Editor version and how you run it (Windows download, or from source);
- your operating system and browser;
- the steps that show the problem;
- what an attacker could do with it.

You get the reply in the same private report.

## What to keep out of reports and issues

- **API keys.** The AI assistant stores the key of your AI provider on your own computer, in `~/.fta_editor/ai_credentials.json`. Never attach that file or paste a key anywhere.
- **Confidential analyses.** Remove or replace confidential names and numbers in analysis files before you attach them.

## How the editor runs

FTA Editor is a local, single-user tool. The web app serves on `127.0.0.1` only and is not meant to be reached from other computers. A report is most useful when it shows a problem in that setting.
