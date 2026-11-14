---
name: embedded-testing-contest-assistant
description: >-
  ETest5 embedded-testing competition playbook (全国大学生软件测试大赛 嵌入式赛项).
  Use when the task involves ETest5, 慕测/mooctest 第三方考试客户端, 覆盖率评分,
  串口/RS232 仿真被测件, 测试序列脚本, 问题报告, or squeezing a score out of a .NET SUT
  via decompilation. Ships a CLI-only toolchain: run sequences, read the score without a
  token, auto-dismiss blocking modal dialogs, decompile the SUT to locate scoring flags,
  export and upload the result ZIP.
---

# 软件测试大赛嵌入式赛项助手 · Embedded Testing Contest Assistant

Act as the implementing agent: inspect the supplied problem and environment, then carry out the applicable setup, testing, diagnosis, reporting and delivery steps using the bundled tools. Adapt to the current problem, report actual evidence and blockers, and follow the user's instructions on submission. Do not ask the user to run routine commands that you can run yourself.

Some past SUTs expose a `getScore()` function and coverage flags. These are problem-specific, not a guaranteed platform scoring model. Read the current rules and requirements first; use decompilation, direct serial access, score queries, or automated submission only when permitted. Confirm results in the official client.

**Scope.** Authorised competition / lab environments only: the SUT, the exam client and the
project file all come from the organiser. Nothing here is meant for testing systems you do not
own. See `README.md` for the human-facing intro, install steps and env vars.

**Before use.** Verify the current competition rules, environment, scoring, allowed tools and submission procedure. Scores, commands, timing, ports, protocols and defaults below are historical observations, not guarantees. Do not assume permission to submit; follow the user’s instructions and the competition rules. The examples require adaptation.

**Repo layout.** `scripts/` = 15 scripts (13 callable from the shell), `references/patterns.md` = protocol notes and three
worked cases, `examples/` = drop-in script templates (task-script and direct-serial styles).

## 0. Environment contract

| Item | Value |
|---|---|
| ETest5 web | `http://localhost:9060` (login `admin` / `123456`) |
| Services | pyserver `:9060`, engine `ETestS5.exe`, node `:12123` |
| Engine log | `%ET5_HOME%\logs\<yyyy_mm_dd>\S0_*.txt` — wait for `task run result = PASSED\|FAILED` |
| Project scripts | `%APPDATA%\.etest5-workspace\<pid>\scripts\*.py` |
| Browser | **only** a persistent Edge/Chrome with `--remote-debugging-port=9333 --user-data-dir=<own profile> --proxy-server=direct://`; connect via CDP. Playwright-launched browsers render the SPA blank. |
| Python | any 3.8+ for these scripts; clear `PYTHONHOME`/`PYTHONPATH` before invoking (a stale `PYTHONHOME` breaks `ctypes`). |

Paths are resolved by `scripts/et5env.py`: `ET5_HOME` → registry → common install dirs.
Override with `ET5_HOME`, `ET5_PY`, `ET5_LOGDIR`, `ET5_CDP` when the defaults are wrong.
`python scripts/et5env.py` prints what it found — run it first on a new machine.

Startup traps that look like broken software:

- Scheduled task stuck in `Running` + `MultipleInstances=IgnoreNew` → later triggers are silently dropped. Use `Parallel`, or `Stop-ScheduledTask` first.
- Engine says `已有任务正在运行` after a hung task → restart `ETestS5.exe`; there is no API to clear it.
- `prepareEnv failed` / `hard_chan==NULL` on an imported project → its `port.cardInstanceId` belongs to another machine. Copy the local card id (see `run.py cards`) and re-bind.

## 1. Thirty-minute plan

| min | Do | Command |
|---|---|---|
| 0-3 | token → download SUT → unzip → skim the requirement doc | exam-client UI |
| 3-7 | health check, import, channel map, bind to local ports | `doctor.py`, `setup.py import/info`, `run.py bind` |
| 7-10 | start the SUT, verify one frame reaches it | `sut.py click/combos`, `protocol.py --pack` |
| 10-13 | **decompile, read `getScore()`**, count both arrays | `decompile.py <exe> --grep` |
| 13-20 | one script covering every flag group; accumulators first | `examples/*` as template |
| 20-24 | run, then ask which flags are still missing | `maximize.py`, `flags.py` |
| 24-32 | close the gaps group by group; submit on every gain | `sweep.py`, `submit.py upload` |
| rest | defect hunt → 问题报告 (verify weighting in current rules) | `sut.py dialogs` log + findings template |

Rule of thumb: if the score does not move after one script, stop writing scripts and run
`flags.py`. The gap list tells you what to write next; guessing costs more than it saves.

## 2. Commands

Commands below assume the current directory is `scripts/`.

```bash
# --- cold start ---
python doctor.py [--fix]                   # services / engine busy / ports, restarts if asked
python setup.py import <project.zip>       # REST import, prints the new pid
python setup.py info <pid>                 # channels, sequences, local COM ports
python run.py cards                        # cardInstanceId in use per project
python run.py bind <pid> Speed=COM2 gas=COM6 --card <uuid> --relines

# --- protocols & frames ---
python protocol.py <pid> --list            # field layout of every protocol
python protocol.py <pid> --pack P_speed speed=60    # byte-exact frame with checksum
python protocol.py <pid> --examples

# --- run & measure ---
python run.py patch <pid>                  # inject ask() auto-answer
python run.py list <pid>
python run.py one <pid> 9 --timeout 300
python run.py all <pid> --last 接口3,功能4
python score_tcp.py                        # score, from :10308, frame FF FF 01 F0
python flags.py                            # per-flag hit list, same port, frame FF FF 01 0F
python score.py --shot s.png               # exam-client fallback (restarts the SUT — wipes flags!)
python maximize.py <pid> <script.py> --seq 1 --rounds 3

# --- diagnose ---
python sweep.py <pid> <seq> --probes probes.txt   # one frame per run, score delta each
python sut.py watch / dialogs / dismiss / capture "<title>" out.bmp / ports
python sut.py screen                       # resolution + DPI scaling + awareness mode
python sut.py combos "<title>"             # list dropdowns of a port dialog
python sut.py combo-set "<title>" 0 COM3   # select by value, never by index

# --- deliver ---
python decompile.py "<SUT.exe>" -o decompiled --grep
python submit.py export <pid> out.zip
python submit.py upload out.zip <token> --shot done.png
```

`protocol.py` packs frames with the engine's own rules (field order, endianness, `CheckCode(SUM_8)`
over cmdType+dataLen+payload). Verify it once against a known-good frame, then you never hand-write
hex again. `replay_snippet.py` replays a frame list from a text file — drop it in a project slot and
`sweep.py` will drive it for you.

## 3. Scoring model

Typical instrumented SUT (verified on two problems):

```csharp
double getScore() {
    foreach (int f in portFlags)   n  += f * 2;   // protocol / UI events
    foreach (int f in ifelseFlags) m  += f * 3;   // value-range branches
    return n + m;
}
```

So a score is a linear system: The total alone may have multiple flag combinations; inspect the individual flag list when available. Never guess after that point — enumerate.

How to attack, in order of payoff:

1. **Range probes.** Designers plant branch flags on intervals absent from the requirement doc
   (e.g. pressure `(5,6] (6,7] (7,8] (8,9]`, flow `(300,301]`, `[499,500)`). Send values that
   land strictly inside each interval, plus the exact boundary.
2. **Stateful sequences.** Counters (`total == 5000`, `[4990,5000)`) require the accumulator to
   start at 0. Restart the SUT, then push the counter in exact steps before anything else runs.
   Order beats data: the same frames in a wrong order can never hit those flags.
3. **Protocol robustness.** Bad header / cmdType / length / payload / checksum / tail, redundant
   prefix, truncated frame, oversized frame, two frames in one write, one frame split in three,
   byte-at-a-time. Each is usually its own flag.
4. **UI events.** Port-config dialog OK/Cancel/reopen, every dropdown item, service start twice,
   stop-then-start (counter reset). Cheap points, easy to forget.

## 4. Hard rules (each one cost hours to learn)

- **Modal dialogs kill everything.** A WinForms message box blocks the SUT's UI thread; all later
  tests fail. Keep `sut.py watch` running as a scheduled task; it also logs dialog bodies, which
  are defect evidence.
- **A task that touches one channel may not bind the others.** First thing in any probe script,
  reference every channel you declared (`channels[name]` in a loop) before sending. Symptom: a
  single-frame probe on the second port does nothing while the same frame works inside a bigger
  script.
- **Screen scale is irrelevant, with one exception.** All UI actions go through window handles
  (`BM_CLICK`), `PrintWindow`, and Playwright element selectors, so 1920×1080 → 2560×1600 at 175%
  changes nothing. The single pixel path is the dialog fallback click: it is proportional
  (70% width / 7.5% height) and the process is per-monitor-DPI-v2 aware, so `GetWindowRect` and
  `SendInput` agree on physical pixels. Run `sut.py screen` first if the display changed.
- **`schtasks.exe` may be blacklisted.** `doctor.py --fix` starts tasks through the PowerShell
  cmdlet `Start-ScheduledTask` first and only falls back to `schtasks /Run`.
- **PYP's `open()` defaults to GBK.** Reading a reply that contains Chinese raises
  `UnicodeDecodeError`, which surfaces as "every command times out". Always
  `open(path, encoding="utf-8", errors="ignore")` inside task scripts.
- **Port dialogs: pick the port by text, not by index.** The item order returned by the driver
  changes between boots, so index-based selection silently binds the wrong port — frames send
  fine and nothing arrives.
- **Every frame gets drained.** `read_buff(0, 400)` after each write, frame gap ≥400 ms; the SUT
  sleeps 300 ms and processes one frame per write, so buffers fill fast.
- **Scripts must end with `stop()`**, otherwise the task runs to timeout and holds the engine.
- **PYP cannot import your modules and cannot spawn subprocesses.** Inline everything; exchange
  data through files.
- **`check(True, ...)` is common in stock scripts.** PASSED then means nothing. Trust only real
  assertions you wrote or read.
- Never send `NaN`/`Inf` or multi-KB garbage: they poison accumulators and kill receive threads.

## 5. Frame delivery is not reliable — plan around it

The SUT typically reads the whole serial buffer in one go and treats the joined hex string as
one packet. Two frames that arrive close together become a "too long" packet and the second is
dropped. Symptoms: fewer rows than frames sent, `score` stuck, a flag that "should" have fired.

Countermeasures, in order:

1. Gap ≥ 600 ms between frames; ≥ 1 s after a warm-up at task start (first frames are lost while
   the port thread settles).
2. **Baud rate matters on virtual ports.** At 9600 com0com delivers byte-by-byte, so an 8-byte
   frame can be split and the SUT (which has no framing logic) drops it. Switch both sides to
   115200 and frames arrive whole — this alone took one problem from 29/47 to 38/47 flags.
3. **Parsing can be state-gated.** A handler that starts with `if (!isStart) return;` silently
   discards everything you send before the "start" action. Read the handler's first lines before
   writing probes; zone/command frames may only count while the device is running.
4. **Bad frames are worse than slow frames.** A malformed or truncated frame throws inside the
   SUT, pops a modal box and blocks that port's thread. Keep `sut.py watch` running and gap
   ≥ 2.5 s after any bad frame, or put all bad frames at the very end.
5. **Run the whole script twice, in two separate task runs.** Flags are sticky but delivery is
   not: the second pass starts with empty buffers and cleared dialogs.
6. For step logic (counters, set-speed), send more steps than needed so drops cannot prevent
   crossing the target value.

## 5.1 When ETest5 tasks get in the way: drive the ports directly

Some problems cannot be solved from a task script at all — the score depends on serial frames
**interleaved with UI actions** (click 开始, wait for a countdown, click 复位). Task starts also
queue up and return `已有任务正在运行` when one hangs.

Because the score lives in the SUT process, it does not matter who sends the frames. Open the
ETest-side COM ports with pyserial, send the same bytes, click buttons with `BM_CLICK`, and read
`:10308`. This removed every queueing problem on the dart problem and ran 3× faster.
Checklist: no ETest task running (or its ports stay busy), engine may need a restart to release
handles, and the exam-client read (`score.py`) **restarts the SUT and wipes flags** — never call
it mid-run.

## 5.2 Two queries on 10308

```
FF FF 01 F0 + float32(1.4)  ->  FF FF 04 <double LE score>                      # score
FF FF 01 0F + float32(1.4)  ->  FF FF <int32 len> <json flag list> <uint32 id>   # per-flag
```

The `0F` reply is a JSON array of `{nodeName, category, ifCatch}` — i.e. **exactly which flags are
still missing**, which turns guessing into a checklist. `flags.py` prints `MISS:`/`GOT:`.

## 6. Historical results (reported by the original author; not independently revalidated)

| Problem | Baseline (stock scripts) | Best | What moved it |
|---|---|---|---|
| Water meter (prelim) | 80 | **100** | one human-paced script; accumulator pushed 4500→4990→5000 first |
| Cruise control | 76 | **100** | decompile → 44-flag table → one script, run twice |
| Dart (dartboard) | 2 | **100** | 47 flags; direct serial + buttons; 115200 baud; zone frames only while started |

Adaptation cost on a fresh problem: 3 min 18 s to decompile and enumerate all 44 flags, ~90 s per
script round. Reusable scripts: `examples/water_max.py`, `examples/cruise_max.py` (task-script
style), `examples/dart_pyp.py` and `examples/dart_host.py` (same problem, task vs. direct-serial
style — diff them to pick the right harness; the PYP example also requires a separate host-side `dart_driver.py` that is not included), `examples/cruise_flags.md` (flag table template).

## 7. Defect report (verify current weighting in the official rules)

One row per defect: ID, requirement clause, expected, actual, reproduction (frame bytes or exact
UI steps), evidence (screenshot path, source snippet, dialog text), severity. Only report what you
can reproduce; an empty section scores zero, a wrong one scores negative.

High-yield defect classes on this platform: threshold/constant mismatch vs. requirement, unit or
scaling errors, boundary not clamped, bad frame accepted, exception instead of discard, counter not
reset, timing requirement violated.

## 8. New problem, cold start

Ten minutes, in this order. Every step has a command; none needs the web UI.

1. `doctor.py` — services up, engine idle, COM ports present. `--fix` starts what is missing.
2. `setup.py import <zip>` — import, get the pid.
3. `setup.py info <pid>` — channels (names, COM, line, baud), sequences, local ports.
4. `run.py cards` then `run.py bind <pid> Name=COMx ... --card <uuid> --relines` — the imported
   project points at the authoring machine's virtual card; this makes it point at yours.
5. Open the SUT, confirm its own port dialog matches the bindings (`sut.py combos "<title>"` lists
   every dropdown and its items; `combo-set` picks by value, never by index), start its service.
6. `protocol.py <pid> --list` then `--pack <proto> field=value` — verify one packed frame against
   a frame the stock scripts already use (byte-identical or fix the packer before continuing).
7. `decompile.py "<SUT.exe>" --grep` — read `getScore()`, write the flag table down. This is the
   step that decides the score: 44 flags on the cruise problem took 3m18s to enumerate.
8. Write one script covering every flag group, then `maximize.py <pid> script.py --seq N --rounds 2`.
9. `flags.py` — whatever is still red, close it with `sweep.py` (one frame per run, score delta per
   step). Only fall back to `score_tcp.py` when the `0F` command is not implemented.

Ordering rules that survive every problem: accumulators first (they need a zeroed counter),
range probes with strictly-inside values, protocol abuse after business frames, destructive frames
last, and the whole script twice.

Deeper protocol/API notes and three worked cases: `references/patterns.md`.
