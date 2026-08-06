---
description: Use one copyable, safety-aware prompt to let a Skill-capable agent install and verify the RunBuoy Skill and CLI.
---

# Install RunBuoy with an Agent

This product-neutral prompt asks your agent to install the RunBuoy Skill, then follow the Skill's built-in safety rules to detect, install, and verify the CLI. It does not start pairing, a demo, or any monitored command.

## Prerequisites

- The agent can install or import a Skill from source; the agent decides which native mechanism to use.
- The computer runs macOS or Linux. Local RunBuoy execution requires Python 3.12+ and `tmux`.
- If `uv` or `tmux` is missing, the agent explains the required system command and waits for approval.

The source is in [`skills/runbuoy` on GitHub](https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy). The installation must preserve `SKILL.md`, `agents/openai.yaml`, and the `references/` directory in full.

## Copy the complete installation prompt

Copy the complete prompt below and paste it into any agent that supports Skills:

```text
Help me install and verify RunBuoy:

1. Use your native Skill installation mechanism to install the RunBuoy Skill from
https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy
Preserve SKILL.md, agents/openai.yaml, and the references/ directory in full. Do not guess an installation path.

2. After installation, read references/installation.md from that Skill and follow its safety rules to install the RunBuoy CLI. First check command -v runbuoy. If it is missing and uv is available, run:
uv tool install --python 3.12 runbuoy

3. If uv or tmux is missing, or sudo, a system package manager, or a curl installer is required, explain the exact command and wait for my approval.

4. Finally run:
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json

Only report whether the Skill is discoverable as $runbuoy, the CLI version, local_ready, and delivery status. Do not start pairing, a demo, or any monitored command, and do not upload logs.
```

The prompt avoids product-specific installation directories, so it works with Codex or any other agent that supports Skills. If an agent cannot install Skills, it should explain the manual method it supports instead of guessing a path.

## Safety boundaries

- An existing CLI is detected first and is not installed again.
- `sudo`, system package managers, and curl installers require your approval.
- Verification only reads the version, `local_ready`, and `delivery` status.
- Installation does not pair an iPhone, run a demo, start a monitored command, or upload logs.

## Use it after installation

In a conversation that supports Skill invocation, use the existing default wording:

```text
Use $runbuoy to monitor this command safely from my iPhone.
```

Provide the complete command in the same request. The agent should run the RunBuoy preflight first, preserve the original command after `--`, and avoid uploading full logs or a shared log tail unless you explicitly request it.
