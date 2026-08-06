import { useState } from 'react';
import { useLang } from '@rspress/core/runtime';
import {
  Button,
  Link,
  copyToClipboard,
} from '@rspress/core/theme-original';
import {
  ArrowRight,
  Check,
  Cloud,
  Copy,
  DeviceMobile,
  Laptop,
  MagicWand,
  ShieldCheck,
  TerminalWindow,
} from '@phosphor-icons/react';

import { localizeHref } from '../../utils/localizeHref';
import './index.css';

const MANUAL_COMMANDS = `uv tool install --python 3.12 runbuoy
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json`;

const AGENT_PROMPTS = {
  zh: `请帮我安装并验证 RunBuoy：

1. 使用你原生支持的 Skill 安装机制，从
https://github.com/TANG617/RunBuoy/tree/main/skills/runbuoy
安装 RunBuoy Skill，完整保留 SKILL.md、agents/openai.yaml 和 references/ 目录，不要猜测安装路径。

2. 安装后读取该 Skill 的 references/installation.md，并按照其中的安全规则安装 RunBuoy CLI。先检查 command -v runbuoy；如果缺失且 uv 已可用，执行：
uv tool install --python 3.12 runbuoy

3. 如果缺少 uv、tmux，或者需要 sudo、系统包管理器或 curl 安装器，请先说明将执行的命令并等待我的确认。

4. 最后运行：
runbuoy --version
runbuoy doctor --json
runbuoy capabilities --json

只汇报 Skill 是否能以 $runbuoy 被发现、CLI 版本、local_ready 和 delivery 状态。不要启动配对、Demo、被监控命令，也不要上传日志。`,
  en: `Help me install and verify RunBuoy:

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

Only report whether the Skill is discoverable as $runbuoy, the CLI version, local_ready, and delivery status. Do not start pairing, a demo, or any monitored command, and do not upload logs.`,
} as const;

const copy = {
  zh: {
    startEyebrow: '推荐安装方式',
    heading: '把安装交给 Agent',
    lead: '复制一条提示词，同时安装 RunBuoy Skill 与 CLI，并完成本机验证。',
    agentBadge: '推荐',
    agentHeading: '安装 Skill + CLI',
    agentLead:
      'Agent 会先检查环境，再按 RunBuoy Skill 中的安全规则执行；涉及系统权限时会暂停并征求确认。',
    agentMeta: ['安装 Skill 与 CLI', '安装后自动验证', '权限操作先确认'],
    promptLabel: '完整安装提示词',
    promptCopy: '复制安装提示词',
    manualEyebrow: '备选方式',
    manualHeading: '或者手动安装 CLI',
    manualLead: '希望逐条控制命令时，可继续使用公开、可执行的 uv 安装流程。',
    steps: [
      ['准备依赖', '确认系统已安装 tmux 与 uv。'],
      ['安装 CLI', '使用独立的 Python 3.12 工具环境安装 RunBuoy。'],
      ['验证环境', '检查版本、local_ready 与 delivery 状态。'],
    ],
    terminalLabel: 'macOS / Linux · Python 3.12',
    commandCopy: '复制命令',
    copied: '已复制',
    availability: 'Agent 安装提示词与手动安装均可立即使用；App Store 版本正在准备中。',
    availabilityLink: '查看当前下载状态',
    guideLink: '查看完整安装与使用指南',
    boundaryEyebrow: '数据边界',
    boundaryHeading: '只传递状态，不搬走工作',
    boundaryLead:
      '任务始终由电脑端掌控。RunBuoy 只把经过筛选的阶段、进度、时间与结果呈现在 iPhone。',
    nodes: [
      ['Mac / Linux', '命令与完整日志留在本机'],
      ['RunBuoy Server', '转发经过筛选的运行状态'],
      ['iPhone', '实时活动、锁定屏幕与灵动岛'],
    ],
    trust: [
      '命令、源码、环境变量与完整日志默认不离开电脑。',
      '开源组件可审计，Server 也可以按需自托管。',
    ],
    privacyLink: '了解隐私与安全边界',
    finalHeading: '让下一次长任务保持可见',
    finalLead: '先完成 Skill 与 CLI 安装；即使尚未配对 iPhone，本地 Run 也可以完整使用。',
    primary: '交给 Agent 安装',
    secondary: '手动安装',
  },
  en: {
    startEyebrow: 'Recommended setup',
    heading: 'Let your agent handle installation',
    lead: 'Copy one prompt to install the RunBuoy Skill and CLI, then verify the machine.',
    agentBadge: 'Recommended',
    agentHeading: 'Install the Skill + CLI',
    agentLead:
      'Your agent checks the environment first and follows the safety rules in the RunBuoy Skill. It pauses for approval before system-level changes.',
    agentMeta: ['Skill and CLI together', 'Verified after install', 'Approval before system changes'],
    promptLabel: 'Complete installation prompt',
    promptCopy: 'Copy install prompt',
    manualEyebrow: 'Alternative',
    manualHeading: 'Or install the CLI manually',
    manualLead: 'Use the public, executable uv flow when you want to control each command yourself.',
    steps: [
      ['Prepare dependencies', 'Make sure tmux and uv are installed on the system.'],
      ['Install the CLI', 'Use an isolated Python 3.12 tool environment for RunBuoy.'],
      ['Verify the machine', 'Check the version, local_ready, and delivery status.'],
    ],
    terminalLabel: 'macOS / Linux · Python 3.12',
    commandCopy: 'Copy commands',
    copied: 'Copied',
    availability:
      'The agent prompt and manual installation are available now. The App Store release is still being prepared.',
    availabilityLink: 'Check current availability',
    guideLink: 'Read the complete setup and usage guide',
    boundaryEyebrow: 'Data boundaries',
    boundaryHeading: 'Send status, not the work itself',
    boundaryLead:
      'Your computer stays in control. RunBuoy presents carefully scoped phases, progress, timing, and results on iPhone.',
    nodes: [
      ['Mac / Linux', 'Commands and full logs stay local'],
      ['RunBuoy Server', 'Relays carefully scoped run status'],
      ['iPhone', 'Live Activities, Lock Screen, Dynamic Island'],
    ],
    trust: [
      'Commands, source, environment variables, and full logs stay on the computer by default.',
      'The open-source components are auditable and the Server is ready to self-host.',
    ],
    privacyLink: 'Learn about privacy and security boundaries',
    finalHeading: 'Keep your next long run visible',
    finalLead:
      'Install the Skill and CLI first. Local Runs remain fully available before you pair an iPhone.',
    primary: 'Install with an Agent',
    secondary: 'Manual install',
  },
} as const;

function HomeContent() {
  const lang = useLang();
  const isEnglish = lang.startsWith('en');
  const value = isEnglish ? copy.en : copy.zh;
  const agentPrompt = isEnglish ? AGENT_PROMPTS.en : AGENT_PROMPTS.zh;
  const [copiedTarget, setCopiedTarget] = useState<'agent' | 'commands' | null>(null);

  const handleCopy = async (text: string, target: 'agent' | 'commands') => {
    const success = await copyToClipboard(text);
    if (!success) return;
    setCopiedTarget(target);
    window.setTimeout(() => setCopiedTarget(null), 1800);
  };

  const nodeIcons = [Laptop, Cloud, DeviceMobile] as const;

  return (
    <div className="runbuoy-home-content">
      <section
        id="agent-install"
        className="runbuoy-start"
        aria-labelledby="runbuoy-home-steps"
      >
        <header className="runbuoy-section-header">
          <p className="runbuoy-section-eyebrow">{value.startEyebrow}</p>
          <h2 id="runbuoy-home-steps">{value.heading}</h2>
          <p>{value.lead}</p>
        </header>

        <article className="runbuoy-agent-install">
          <div className="runbuoy-agent-install__intro">
            <span className="runbuoy-agent-install__badge">
              <MagicWand size={17} weight="bold" aria-hidden="true" />
              {value.agentBadge}
            </span>
            <h3>{value.agentHeading}</h3>
            <p>{value.agentLead}</p>
            <ul>
              {value.agentMeta.map(item => (
                <li key={item}>
                  <Check size={16} weight="bold" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="runbuoy-agent-prompt">
            <div className="runbuoy-agent-prompt__bar">
              <span>{value.promptLabel}</span>
              <button
                type="button"
                onClick={() => handleCopy(agentPrompt, 'agent')}
              >
                {copiedTarget === 'agent' ? (
                  <Check size={16} weight="bold" aria-hidden="true" />
                ) : (
                  <Copy size={16} weight="bold" aria-hidden="true" />
                )}
                <span aria-live="polite">
                  {copiedTarget === 'agent' ? value.copied : value.promptCopy}
                </span>
              </button>
            </div>
            <pre tabIndex={0}>
              <code>{agentPrompt}</code>
            </pre>
          </div>
        </article>

        <div id="manual-install" className="runbuoy-manual-install">
          <header className="runbuoy-manual-install__header">
            <p className="runbuoy-section-eyebrow">{value.manualEyebrow}</p>
            <h3>{value.manualHeading}</h3>
            <p>{value.manualLead}</p>
          </header>

          <div className="runbuoy-start__grid">
            <ol className="runbuoy-flow">
              {value.steps.map(([title, detail], index) => (
                <li key={title}>
                  <span className="runbuoy-flow__number" aria-hidden="true">
                    {index + 1}
                  </span>
                  <span>
                    <strong>{title}</strong>
                    <span>{detail}</span>
                  </span>
                </li>
              ))}
            </ol>

            <div className="runbuoy-terminal">
              <div className="runbuoy-terminal__bar">
                <span>
                  <TerminalWindow size={18} weight="duotone" aria-hidden="true" />
                  {value.terminalLabel}
                </span>
                <button
                  type="button"
                  onClick={() => handleCopy(MANUAL_COMMANDS, 'commands')}
                >
                  {copiedTarget === 'commands' ? (
                    <Check size={16} weight="bold" aria-hidden="true" />
                  ) : (
                    <Copy size={16} weight="bold" aria-hidden="true" />
                  )}
                  <span aria-live="polite">
                    {copiedTarget === 'commands' ? value.copied : value.commandCopy}
                  </span>
                </button>
              </div>
              <pre className="runbuoy-home-command" tabIndex={0}>
                <code>{MANUAL_COMMANDS}</code>
              </pre>
            </div>
          </div>
        </div>

        <div className="runbuoy-start__foot">
          <p className="runbuoy-home-availability">
            {value.availability}{' '}
            <Link href={localizeHref('/download', lang)}>
              {value.availabilityLink}
            </Link>
          </p>
          <Link
            className="runbuoy-inline-link"
            href={localizeHref('/guide/#agent-install', lang)}
          >
            {value.guideLink}
            <ArrowRight size={16} weight="bold" aria-hidden="true" />
          </Link>
        </div>
      </section>

      <section
        className="runbuoy-boundary"
        aria-labelledby="runbuoy-home-boundary"
      >
        <header className="runbuoy-section-header">
          <p className="runbuoy-section-eyebrow">{value.boundaryEyebrow}</p>
          <h2 id="runbuoy-home-boundary">{value.boundaryHeading}</h2>
          <p>{value.boundaryLead}</p>
        </header>

        <div className="runbuoy-boundary__card">
          <div className="runbuoy-boundary__flow">
            {value.nodes.map(([title, detail], index) => {
              const NodeIcon = nodeIcons[index];
              return (
                <div className="runbuoy-boundary__node-wrap" key={title}>
                  <article className="runbuoy-boundary__node">
                    <span aria-hidden="true">
                      <NodeIcon size={27} weight="duotone" />
                    </span>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                  </article>
                  {index < value.nodes.length - 1 && (
                    <ArrowRight
                      className="runbuoy-boundary__arrow"
                      size={24}
                      weight="bold"
                      aria-hidden="true"
                    />
                  )}
                </div>
              );
            })}
          </div>

          <div className="runbuoy-boundary__trust">
            <ShieldCheck size={28} weight="duotone" aria-hidden="true" />
            <ul>
              {value.trust.map(item => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            <Link
              className="runbuoy-inline-link"
              href={localizeHref('/privacy', lang)}
            >
              {value.privacyLink}
              <ArrowRight size={16} weight="bold" aria-hidden="true" />
            </Link>
          </div>
        </div>
      </section>

      <section className="runbuoy-final-cta">
        <div>
          <p className="runbuoy-section-eyebrow">RunBuoy</p>
          <h2>{value.finalHeading}</h2>
          <p>{value.finalLead}</p>
        </div>
        <div className="runbuoy-final-cta__actions">
          <Button
            type="a"
            theme="brand"
            href={localizeHref('/guide/#agent-install', lang)}
            className="runbuoy-final-cta__primary"
          >
            <MagicWand size={19} weight="bold" aria-hidden="true" />
            {value.primary}
          </Button>
          <Button
            type="a"
            theme="alt"
            href={localizeHref('/guide/#manual-install', lang)}
          >
            <TerminalWindow size={19} weight="bold" aria-hidden="true" />
            {value.secondary}
          </Button>
        </div>
      </section>
    </div>
  );
}

export { HomeContent };
