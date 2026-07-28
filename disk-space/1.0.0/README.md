# sono-plugin-disk-space — 动态板块「磁盘余量」

Sono 社区插件（监看型）：在刘海面板上显示系统卷与数据卷还剩多少空间，切到这一站就是最新的。零动作、纯本地、无披露——这是**快线审核**的样本形态：不联网、不读文件内容、不写任何东西。

这个仓库同时是「第三方作者仓库」的示范：插件内容住在作者自己的仓库里，注册表（[`moonbiuus/sono-plugins`](https://github.com/moonbiuus/sono-plugins)）只存一条指向这里的上架条目（仓库 + tag + 文件哈希）。

## 数据从哪来

`shutil.disk_usage`（底层是 statfs）对两个挂载点的即时读数，**只读卷的容量元数据，不读任何文件内容**：

| 挂载点 | 卷名 | 说明 |
| --- | --- | --- |
| `/` | 系统卷 | APFS 密封系统快照 |
| `/System/Volumes/Data` | 数据卷 | 用户文件实际所在，通常是最紧的那个 |

- 数据是本地即时读取，每次刷新就是当下的真值，所以行内不需要「N 分钟前的快照」标注。
- 两条路径指向同一设备时（非 APFS 分卷布局）只画一行；查不到的卷不画；两个都查不到时降级为一行 `note` 说明——不编造未观测到的状态。
- GB 用十进制口径（1 GB = 10⁹ 字节），与 Finder / 磁盘工具一致。APFS 卷共享容器剩余空间，两行的「剩」可能相同，这是文件系统的事实，不是 bug。
- headline 写最紧的卷（已用比例最高的那个）；已用 ≥ 80% 时加「注意：」前缀。量在 `badge` 里成列对齐，headline 不写计数。

## 文件

- `disk-space.py` — 全部实现，单文件 Python（系统自带 python3 即可，无第三方依赖）。子命令：`refresh`（输出板块数据面 JSON）。
- `spec.json` — 板块声明。`actions` 为空是刻意的：余量是读的东西，没有可执行的动词。
- `manifest.json` — 插件元数据与披露（四个键全为空数组：无网络、无读路径、无写路径、无派生进程）。
- `preview.json` — 商店预览用的示例数据面。

## 本地安装（不走商店时）

```sh
mkdir -p ~/.sono/boards/bin/disk-space
cp disk-space.py ~/.sono/boards/bin/disk-space/disk-space.py
/Applications/Sono.app/Contents/Helpers/sono board install --file spec.json
```

退出码 4（等待批准）是正常的第一步；在面板里批准后上轨。

## 提交自查

按 [`PLUGIN-AUTHORING.md`](https://github.com/moonbiuus/sono-plugins/blob/main/docs/PLUGIN-AUTHORING.md) §5 清单逐条自查的结果（2026-07-28）：

- [x] **确切环境实测**：`env -i PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin HOME="$HOME" LANG=zh_CN.UTF-8 ./disk-space.py refresh </dev/null | python3 -m json.tool` 输出合法 JSON，耗时约 0.6 秒（几乎全是 Python 解释器启动；预算 10 秒）。
- [x] **降级路径**：statfs 失败的卷被跳过、不画行；两个卷都失败时输出 headline「查不到任何卷的容量」+ 一行 note，仍是合法 JSON、零退出。非零退出只发生在子命令拼错时（脚本被误用，不是数据源坏了）。
- [x] **动作命令**：无动作，无需逐个验证。
- [x] **披露与代码一致**：脚本 import 仅 `json` / `os` / `shutil` / `sys`；无网络库、无 `subprocess`、无 `open()`、无写文件——`disclosures` 四个键全空与代码逐条对得上。
- [x] **数据面规则**：headline 写最要紧的事不写计数；量放 `badge`；查不到的不画、用 note 说明；无 toggle（无语义陷阱可踩）；rows 不引用任何 action。
- [x] **脚本形态**：可读纯文本 Python，无混淆、无二进制、不经 shell（argv 数组直启）、运行时不下载执行任何代码、不写 `~/.sono/` 下任何路径。

## 已知边界

- 只看 `/` 与 `/System/Volumes/Data` 两个挂载点，不枚举外接盘和其他 APFS 卷——枚举挂载表要么派生 `mount` 进程、要么读 `/Volumes/`，都会引入本插件刻意保持为零的披露面。需要监看外接盘时应另做一个插件，而不是给这个加开关。
- 「已用」按 statfs 的 `total - free` 计算；APFS 的快照与可清除空间会让这个数与「关于本机」的口径略有出入，取 Finder 同款十进制 GB 已是最接近用户直觉的口径。
