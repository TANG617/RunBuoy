---
description: Install the RunBuoy Skill with a copyable, agent-neutral prompt, then invoke it as $runbuoy to monitor commands safely.
---

# Install the Agent Skill

The RunBuoy Skill gives AI agents with native Skill support the correct preflight, launch, inspection, and privacy rules. It does not replace the RunBuoy CLI.

## Prerequisites

- The agent can install or import a Skill from source; the agent decides which native mechanism to use.
- The `runbuoy` CLI is installed and executable on the computer.
- Installation copies only Skill files. It must not start pairing, a demo, or any monitored command.

The source is in [`skills/runbuoy` on GitHub](https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy). The installation must preserve `SKILL.md`, `agents/openai.yaml`, and the `references/` directory in full.

## Ask your agent to install it

Copy the complete prompt below and paste it into any agent that supports Skills:

```text
Use your native Skill installation mechanism to install the RunBuoy Skill from https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy. Preserve SKILL.md, agents/openai.yaml, and the references/ directory in full. During installation, do not start pairing, a demo, or any monitored command. After installation, only confirm that the Skill can be discovered as $runbuoy. If you do not support installable Skills, clearly explain the manual method you do support and do not guess an installation path.
```

The code block includes a copy button. The prompt avoids product-specific installation directories, so it works with Codex or any other agent that supports Skills.

## Use it after installation

In a conversation that supports Skill invocation, use the existing default wording:

```text
Use $runbuoy to monitor this command safely from my iPhone.
```

Provide the complete command in the same request. The agent should run the RunBuoy preflight first, preserve the original command after `--`, and avoid uploading full logs or a shared log tail unless you explicitly request it.
