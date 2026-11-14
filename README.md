# 软件测试大赛嵌入式赛项助手 · Embedded Testing Contest Assistant

面向全国大学生软件测试大赛嵌入式赛项的 AI Skill 与 ETest5 工具集。它把环境检查、工程导入、串口与协议分析、测试脚本执行、覆盖情况排查、问题报告和结果导出串成一套可复用的工作流，适合使用 ETest5 的预选赛、省赛备赛及授权实验。

> 赛题、平台版本和规则可能不同。使用前请核对当届赛事要求及允许使用的工具；案例成绩仅代表原有记录，不保证其他赛题获得相同结果。

## 能做什么

- **准备环境**：定位 ETest5、检查服务与串口、导入工程并重新绑定本机通道。
- **分析和执行测试**：查看协议字段、组装报文、运行测试序列，辅助定位边界条件与状态相关问题。
- **排查覆盖情况**：在兼容的被测件上读取分数和逐项标志，结合探测结果补充测试。
- **处理运行障碍**：辅助诊断任务阻塞、端口绑定和窗口弹框等问题。
- **整理交付**：导出工程结果包；在环境和规则允许时辅助上传，并依据实际复现结果整理问题报告。

`SKILL.md` 提供给 AI 助手工作流；`scripts/` 是本地辅助工具，既可供助手调用，也可由使用者在终端运行。工具针对历史 ETest5 环境编写，不保证兼容所有平台版本或被测件。

## 安装 Skill

1. 克隆本仓库，或下载 ZIP 并解压为 `embedded-testing-contest-assistant` 文件夹。
2. 将整个文件夹复制到你的技能目录，例如 Codex 的 `~/.codex/skills/embedded-testing-contest-assistant/`。
3. 刷新技能列表或重启客户端。使用时可以说：“使用 embedded-testing-contest-assistant，帮我分析这道嵌入式测试题。”

请保留 `SKILL.md`、`scripts/`、`references/` 和 `examples/` 的相对位置。安装 Skill 不会自动安装 ETest5 或其他依赖。

## 环境准备

| 组件 | 用途 |
| --- | --- |
| Windows、Python 3.8+ | 运行辅助脚本；窗口操作依赖 Win32 |
| ETest5 与赛事提供的工程、被测件 | 测试平台和题目环境 |
| 虚拟串口及对应驱动 | 串口通信；具体按题目和平台配置 |
| Python 依赖 | 在仓库目录执行 `python -m pip install -r requirements.txt` |
| .NET SDK、`ilspycmd` | 可选；仅在允许且需要分析 .NET 程序时使用 |
| Playwright 和可连接的浏览器 | 可选；用于部分考试客户端操作和截图 |

可设置 `ET5_HOME` 指向安装目录；未设置时，脚本会尝试从注册表和常见目录探测。`ET5_PY`、`ET5_LOGDIR`、`ET5_BASE`、`ET5_CDP` 等可覆盖相应默认配置，具体见 `scripts/et5env.py` 和 `SKILL.md`。

## 快速开始

在仓库根目录打开 PowerShell：

```powershell
# 按实际路径修改；也可不设置并尝试自动探测
$env:ET5_HOME = 'D:\Code\ETest5'
python scripts/et5env.py
python scripts/doctor.py
```

根据题目与实际环境，通常按以下顺序推进：

1. 阅读当前赛题、评分和提交要求，确认工具使用范围。
2. 导入工程，检查测试序列、虚拟串口和本机通道绑定。
3. 启动被测件，验证协议和报文收发，再编写或调整测试脚本。
4. 执行测试、查看真实断言和可用覆盖信息，补充边界与状态测试。
5. 复现并记录缺陷，核对结果包；按用户指示及赛事要求提交。

常用命令示例（尖括号内容为需要替换的参数，不能原样运行）：

```text
python scripts/setup.py import <工程ZIP>
python scripts/setup.py info <项目ID>
python scripts/run.py cards
python scripts/run.py bind <项目ID> 通道名=COM2 --card <本机卡ID> --relines
python scripts/protocol.py <项目ID> --list
python scripts/run.py one <项目ID> <序列编号> --timeout 300
python scripts/flags.py
python scripts/submit.py export <项目ID> <输出ZIP>
```

`flags.py` 和 `score_tcp.py` 依赖被测件提供兼容的本地接口，并非所有赛题都可用。`score.py` 通过客户端读取时可能重启被测件并清空当前覆盖状态；运行前请先确认。自动修复、导入、绑定和上传等操作会改变环境或结果，执行前应了解其影响。

## 历史案例

原有资料记录了水流计费器、车载控制和智能飞镖等赛题的测试经验，包含达到 100 分的案例；具体脚本与过程见 `examples/`、`references/patterns.md` 和 `SKILL.md`。这些记录没有随仓库提供完整的官方回执，本次整理也未重新运行赛题，因此不能作为当前平台成绩或通用满分能力的验证。

示例需按题目和本机端口调整。`examples/dart_pyp.py` 依赖未包含的宿主侧 `dart_driver.py` 和共享目录，不能单独运行；`dart_host.py` 是另一种直连串口的示例。

## 常见问题

- **找不到 ETest5**：先运行 `python scripts/et5env.py`，检查安装路径，必要时设置 `ET5_HOME`。
- **工程无法准备环境**：检查导入工程中的通道、串口及虚拟卡 ID 是否与本机一致。
- **任务显示通过但结果不变**：检查测试脚本中的断言和实际报文，`PASSED` 本身不等于覆盖目标已达成。
- **报文发出但被测件没有响应**：核对两端串口、波特率、帧格式、启动状态和发送间隔；历史案例中的设置不一定适用于新题。
- **窗口操作出现 Python 环境异常**：检查是否有不兼容的 `PYTHONHOME` 或 `PYTHONPATH` 环境变量。

## 目录

| 路径 | 内容 |
| --- | --- |
| `SKILL.md` | AI 助手使用的工作流与命令参考 |
| `scripts/` | ETest5 环境、协议、执行、诊断和导出工具 |
| `references/patterns.md` | 协议、接口和历史案例说明 |
| `examples/` | 针对特定历史赛题的脚本示例 |
| `requirements.txt` | Python 依赖 |

## 使用范围与许可

请仅在获得授权的竞赛、备赛或教学环境中使用，并遵守当届规则。项目以 [MIT License](LICENSE) 发布。
