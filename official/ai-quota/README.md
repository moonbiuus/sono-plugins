# ai-quota-board — 动态板块「AI 额度」

官方插件（监看型范本）：在刘海面板上显示 Claude Code 与 Codex 订阅额度的剩余，切到这一站就是最新的。零动作、纯刷新——与控制型范本 [`agents/audio-board/`](../audio-board/) 互补，社区作者做监看类插件从这里抄骨架。

## 数据从哪来

| 来源 | 通道 | 新鲜度 |
| --- | --- | --- |
| Claude（5 小时 / 一周窗口） | 钥匙串项 `Claude Code-credentials`（`claude` CLI 登录后写入）或 `~/.claude/.credentials.json` 里的 OAuth token → `api.anthropic.com/api/oauth/usage` | 每次刷新实时查询 |
| Codex（当前账户上报的窗口） | `~/.codex/sessions/**.jsonl` 里 Codex 自己记录的 `rate_limits` 快照，纯本地读取 | 等于 Codex 上次运行的时刻，行内标注「N 分钟前的快照」 |

**查不到的窗口不画。** 实测（2026-07，Codex pro 账户）Codex 只上报一个一周窗口、没有 5 小时窗口——板块按观测到的画；将来快照里出现新窗口会自动多一行。每一种「查不到」都有对应的 `note` 行写明原因与修法（未登录 → 提示 `/login`；无快照 → 提示跑一次 Codex），这是数据面「未知不渲染成确定」的范本用法。

## 文件

- `ai-quota.py` — 全部实现，单文件 Python（系统自带 python3 即可，无第三方依赖）。子命令：`refresh`（输出板块数据面 JSON）。
- `spec.json` — 板块声明，`sono board install --file spec.json` 写入（哈希由 CLI 现算）。`actions` 为空是刻意的：额度是读的东西，没有可执行的动词。
- `manifest.json` — 插件元数据与披露（社区分发格式，见 [`docs/PLUGIN-AUTHORING.md`](../../docs/PLUGIN-AUTHORING.md)）。
- `preview.json` — 商店预览用的示例数据面。

## 安装

```sh
mkdir -p ~/.sono/boards/bin/ai-quota
cp ai-quota.py ~/.sono/boards/bin/ai-quota/ai-quota.py
/Applications/Sono.app/Contents/Helpers/sono board install --file spec.json
```

退出码 4（等待批准）是正常的第一步；在面板里批准后上轨。

## 已知边界

- **Claude 一侧要求 `claude` CLI 登录过**（钥匙串里有 `Claude Code-credentials`）。只用桌面 App 的用户拿不到 token——桌面端凭据是 Electron 加密存储，脚本刻意不去碰。未登录时显示一行说明，不装死也不报错。
- 首次读钥匙串可能弹「security 想访问」系统对话框；脚本对钥匙串调用设 4 秒超时，超时后在板块上写明「先在终端跑一次并选始终允许」。批准是用户的事，脚本不等它。
- Claude 用量接口是 OAuth 侧的非公开接口，字段按防御式解析：认不出的字段跳过，全认不出时在板块上明说，不静默出错。
- 脚本不写任何文件，无缓存；刷新只在用户切到这一站时发生，频率天然有上限。
