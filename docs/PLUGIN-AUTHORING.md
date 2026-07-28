# Sono 插件制作规范（面向 Agent）

状态：**草案**，随 [`DESIGN-COMMUNITY.md`](DESIGN-COMMUNITY.md) 的决策定稿。定稿后同步到注册表仓库 `moonbiuus/sono-plugins`，那里的副本是对外事实源。

这份文档写给**替用户制作插件的 Agent**。它自包含：照着做就能从零做出、验证并提交一个能上架的插件，不需要读过 Sono 的其他设计文档。用户把本文整篇贴给你时，你的任务通常是其中一段——先确认用户要的是「做一个」「装一个」还是「发布一个」。

---

## 1. 你在做什么

一个 **Sono 插件**是一个目录，装着一个**动态板块**：Sono（macOS 刘海上的 Agent 交互层）会按你的声明渲染一站界面，并在用户切到这一站或点击动作时，替你跑你声明的命令。你不需要常驻进程，不需要写 UI 代码——**界面是声明出来的，执行是 Sono 代跑的**。

必须先理解的三件事：

1. **执行环境是敌意的简朴。** 你的脚本跑在一个放弃了 Sono 全部系统授权的子进程里：10 秒超时（动作可声明至多 60 秒）、stdin 是 `/dev/null`、stdout 上限 256KB、环境变量只有 `PATH` / `HOME` / `LANG`、不经过 shell。在终端里能跑不等于在 Sono 里能跑，§5 的验证配方是唯一判据。
2. **用户会逐条批准你的命令。** 安装后 Sono 向用户展示每条命令的完整 argv 和脚本哈希，批准后才会执行；**脚本内容一变，授权当场失效**，板块停摆等待重批。所以：迭代期每改一次脚本用户要重批一次，这是机制不是 bug。
3. **界面词表是封闭的。** 只有三种行（见 §4），没有滑块、没有输入框、没有嵌套、没有自定义像素。做不出来的界面就是不该做的界面——把需求收敛进词表，而不是对抗词表。

## 2. 插件目录布局

**插件住在你自己的 GitHub 仓库里**——star、issue、README 都是你的；注册表只存一条指向你的上架条目（仓库 + tag + 文件哈希）。插件包默认是仓库根目录；monorepo 放子目录，上架时用 `path` 指明。

```
<你的仓库>/<path>/
  manifest.json     元数据与披露（§3）
  board.json        板块声明：显示名、图标、命令（§4.1）
  <你的脚本>         文本脚本（sh / py / js…），可多个
  README.md         商店详情页正文：它做什么、数据从哪来、已知边界
  preview.json      可选：一份示例数据面 JSON，商店预览时由 Sono 渲染
```

**id 规则**：ASCII 短横线风格（`ai-quota`），不能为空、不含 `/` `\` `:`、空白或换行，≤100 字符，在注册表里唯一。中文放 `name`。

## 3. manifest.json

```json
{
  "manifestVersion": 1,
  "id": "ai-quota",
  "name": "AI 额度",
  "version": "1.0.0",
  "description": "Claude Code 与 Codex 的订阅额度，切到这一站就是最新的。",
  "author": { "name": "你的名字", "github": "你的 GitHub 用户名" },
  "contentType": "board",
  "minSonoVersion": "0.6.0",
  "license": "MIT",
  "category": "monitor",
  "files": { "board": "board.json", "scripts": ["ai-quota.py"], "preview": "preview.json" },
  "disclosures": {
    "network": ["api.anthropic.com"],
    "reads": ["~/.codex/sessions/", "钥匙串项 Claude Code-credentials"],
    "writes": [],
    "spawns": ["/usr/bin/security"]
  }
}
```

- `category` 四选一：`system`（控制系统或 App）/ `monitor`（监看状态）/ `info`（信息聚合）/ `dev`（开发工具）。
- `version` 用 semver，提交更新时必须递增。
- **`disclosures` 是披露，不是权限**：Sono 没有沙盒，声明不会给你能力，也不会限制你——它是你对审核者和用户的陈述。四个键分别列：会访问的网络主机、会读的路径或凭据存储、会写的路径、会派生的其他程序。**披露与代码不符是最常见的拒收原因**。空的键写 `[]`，不要省略。
- `description` 一句话写用途与更新时机，不写形容词。

## 4. 板块怎么写

### 4.1 board.json（执行面）

```json
{
  "version": 1,
  "board": "ai-quota",
  "displayName": "AI 额度",
  "icon": "gauge",
  "exec": {
    "file": "~/.sono/boards/bin/ai-quota/ai-quota.py",
    "refresh": { "argv": ["${exec.file}", "refresh"] },
    "actions": [
      { "id": "recheck", "label": "重新查询", "impact": "low",
        "argv": ["${exec.file}", "refresh"] }
    ]
  }
}
```

- `icon` 是 SF Symbol 名。
- `refresh.argv` 在用户**切到这一站**和**每次动作执行完之后**运行，stdout 就是界面（§4.2）。没有定时轮询——用户没在看时你的代码不会跑，不要按「每分钟采样」设计。
- `actions` 可以为空（纯监看板块）。每个动作 0–60 秒超时（`timeoutSeconds`，默认 10）；`impact: "high"` 的动作 Sono 会就地二次确认，可配 `confirm` 文案——不可逆或影响别人的动作（退出 App、删除、发送）必须标 high。
- argv 是数组，**不经 shell**：不要写 `sh -c`（拒收线），不要指望通配符展开。仅有的两个插值是 `${exec.file}` 与 `${row.id}`（后者作为单个 argv 元素传入，注入在结构上不成立）。
- **`sha256` 不要写**——安装时自动计算。
- **密钥永远不进 argv**。执行审计记录完整 argv；要传凭据走文件或钥匙串。

### 4.2 刷新命令的 stdout（数据面）

输出一份 JSON 到 stdout：

```json
{
  "headline": "最紧的是 Claude 5 小时窗口：已用 78%",
  "rows": [
    { "kind": "row", "id": "claude-5h", "title": "Claude · 5 小时",
      "detail": "已用 78% · 今天 16:00 重置", "badge": "剩 22%" },
    { "kind": "toggle", "id": "com.apple.Music", "title": "静音",
      "on": true, "action": "toggle-mute" },
    { "kind": "note", "text": "Codex：会话文件里暂无额度快照" }
  ]
}
```

三种行：

| kind | 画什么 | 用途 |
| --- | --- | --- |
| `row` | 标题 + 可选 `detail` / `badge` + 0..3 个动作引用 | 主力 |
| `toggle` | 一个命题 + 它此刻成不成立（`on`）+ 一个翻转它的动作 | 开关 |
| `note` | 一行说明，无动作 | 空态、错误、数据来源脚注 |

**规则，每条都有事故背书，违反会被审核打回：**

1. **`toggle.title` 命名 `on == true` 时成立的那件事**，不是它控制的对象。`title: "静音", on: true` 读作「静音是开着的」✅；`title: "系统输出", on: true`（on 装的却是静音状态）会被读成「输出开着」——语义正好相反。一个说反的开关比没有开关更危险。
2. **`toggle` 的动作必须把状态翻到另一侧。** Sono 把它画成开关控件，不是按钮。
3. **`on` 查不到就整个省略这个键**——那时 Sono 退回画按钮并标「状态未知」。未知不等于 false，编一个值等于让界面断言它没观测到的事。
4. **`headline` 不写计数**（「6 个窗口」是零行动信息），写此刻最要紧的那件事（「最紧的是……」「全部充足」「数据源断了」）。
5. **量放 `badge`**（等宽数字右对齐成列），不埋在 `detail` 正文里。
6. **数据来源与新鲜度写出来**：来自缓存或快照的数据，在 `detail` 或 `note` 里写「N 分钟前的快照」。查不到的东西**不画行**，用一行 `note` 说明为什么查不到、用户怎么修（「claude CLI 未登录：运行 claude 后输入 /login」）——诚实降级是这个平台的品味底线。
7. `rows[].actions` 只能引用 board.json 里已声明的 action id，**写不出内联命令**——数据面在语法上就改不了执行面，这是刻意的。
8. 一行最多 3 个动作，超了整行会被降级成说明；认不出的 kind 会被画成「当前版本不认识这一行」——所以老老实实用这三种。

### 4.3 脚本本身

- **必须是可读文本**（sh / python / js / rb…）。二进制、混淆、压缩过的代码直接拒收。用户能打开读你的脚本是这个生态的信任基础之一。
- `PATH` 固定为 `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`。需要别的路径在脚本里写绝对路径，不要指望用户的 shell 配置。
- 网络请求自带超时（刷新总预算 10 秒），失败输出带 `note` 的合法 JSON，**不要让脚本非零退出去表达「数据源坏了」**——非零退出 = 板块停摆，那是给「脚本自身坏了」保留的信号。
- **运行时不得下载并执行代码**（拒收线）。`network` 披露只允许出现在读数据的语境。
- 不要写 `~/.sono/` 下不属于你的路径；缓存写在自己的脚本目录旁。

## 5. 本地验证（提交前必须跑）

用 Sono 执行你时的**确切环境**跑刷新命令——这是「在终端好好的，在 Sono 里坏了」唯一的预防手段：

```bash
env -i PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin \
  HOME="$HOME" LANG=zh_CN.UTF-8 \
  ./你的脚本 refresh </dev/null | python3 -m json.tool
```

核对清单：

- [ ] 输出是合法 JSON，且 10 秒内完成（掐表，别估）
- [ ] 数据源不可用时（断网、依赖缺失）输出仍是合法 JSON + note，而不是报错退出
- [ ] 每个动作命令各跑一遍，非零退出只发生在「真的失败」时
- [ ] 本地装一遍走完全流程：`sono board install --file board.json`，退出码 **4 是正常的**（等待用户批准），在面板里批准后切到这一站看真实渲染
- [ ] `sono plugin lint <目录>` 通过（CLI 落地前：对照本文 §3–§4 自查）

`sono` CLI 在 `Sono.app/Contents/Helpers/sono`（或设置 → 板块 → 安装命令行工具）。安装类退出码：`0` 已授权在轨 / `4` 等待批准 / `5` 已被撤销 / `6` 哈希不匹配停摆。

## 6. 安装方式（给「帮用户装插件」的 Agent）

| 场景 | 路径 |
| --- | --- |
| 用户要装社区插件 | 让用户打开 设置 → 插件 → 社区，点安装。**不要**替用户绕过商店去手动抓文件——商店装的有哈希校验和更新通道，手动装的没有 |
| 用户要装你刚做的本地插件 | 脚本放 `~/.sono/boards/bin/<id>/`，声明 `sono board install --file board.json`（或直接写 `~/.sono/boards/<id>.json`，目录被监听，落盘即生效） |
| 装完之后 | 提醒用户：面板里会出现授权卡，需要**用户本人**批准。你批不了，也不要试 |

## 7. 发布到社区

1. 插件目录放进用户自己的 GitHub 仓库，打一个 tag（如 `1.0.0`；monorepo 建议 `plugin-<id>-1.0.0`）。**上架后不要删除或改写这个 tag**——索引钉死了它的文件哈希，改写等于自我下架（注册表会切到镜像并标注「作者仓库已失联」）。
2. 自查：§5 清单全绿；`disclosures` 与代码逐条对得上；README 写清用途、数据来源、已知边界（学 `agents/audio-board/README.md` 的坦率程度——已知认错东家的场景都写出来了）。
3. Fork `moonbiuus/sono-plugins`，在 `plugins/<id>.json` 写上架条目：你的仓库地址、tag、（可选）path。**哈希不用写**——CI 拉取内容自动计算写回。
4. 提 PR。CI 跑结构校验与披露一致性扫描；审核分两级：**纯本地只读**（不联网、不写文件、不碰凭据）走快线，含网络、凭据或系统控制的走人工通读。审核清单公开在仓库 `docs/REVIEW-CHECKLIST.md`，照着自查能省一轮往返——想走快线，就把插件做成不需要网络的样子。
5. 合入即上架。更新 = 打新 tag + 提 PR 改条目的 tag，**每个版本重新过审**；用户侧更新后板块会自动停摆等待重新批准——这是机制保证的，不要试图「让更新无感」。

**作为 Agent 你能代办到提 PR 为止**；GitHub 身份、授权批准、以及「要不要发布」本身，都是用户的决定。

## 8. 两个官方范本

两个官方插件的「作者仓库」就是 Sono 主仓（官方与社区同规则上架，不走后门）：

| 范本 | 学什么 |
| --- | --- |
| `agents/ai-quota-board/`（监看型） | 零动作纯刷新、双数据源（本地文件 + 网络 API）、每一种查不到都有对应的 note、badge 表量、新鲜度标注 |
| `agents/audio-board/`（控制型） | toggle 语义、impact 分级、`${row.id}` 用法、README 如何坦率写已知边界 |

做监看类抄前者的骨架，做控制类抄后者的。两个都读一遍再动手，比读十遍规则有用。
