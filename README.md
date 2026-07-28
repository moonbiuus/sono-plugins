# sono-plugins — Sono 插件社区注册表

[Sono](https://github.com/moonbiuus/sono) 是面向 macOS 刘海的 Agent 交互层；插件给它的刘海面板加一站可刷新、可执行动作的动态板块。这个仓库是插件的**官方注册表**：Sono 客户端从这里拉索引，用户在 设置 → 插件 → 社区 里看到的就是这里的内容。

## 索引制怎么工作

**内容住作者仓库，索引钉死哈希，镜像只做兜底。**

1. **插件内容住在作者自己的仓库里。** star、issue、README、传播节点全部归作者；注册表只存一条上架条目（`plugins/<id>.json`）：作者仓库地址 + 钉死的 tag（+ monorepo 的 `path`）。
2. **索引钉死每个已审版本的文件哈希。** CI 按 tag 取内容、校验结构、算每个文件的 sha256，汇总成 `index.json`。审核的对象是**内容快照**，不是作者：作者事后改 tag、rewrite 历史、换 release 资产，客户端一比哈希就拒装。想发新内容只有一条路——打新 tag、提 PR、重过审核。
3. **镜像是给「作者消失」准备的，不是给分发准备的。** 上架合入时 CI 把该 tag 的内容自动备份进 `mirror` 分支。安装默认从作者仓库拉；作者仓库失联（删库、404、哈希对不上）时自动落到镜像——镜像与索引哈希是同一份字节，用户无感知。
4. **安装不跳过授权卡。** 审核挡「来路不明」，Sono 客户端的逐命令授权卡挡「装了之后它干别的」——两道门防的不是同一件事，任何一道都不替代另一道。脚本内容一变（包括正常更新），授权当场失效，板块停摆等用户重批。

## 仓库布局

```
index.json                  自动生成的总索引（CI 产物，不手改）
plugins/<id>.json           上架条目：作者仓库、tag、path、审核记录
official/                   官方插件内容（临时安排，见下）
docs/PLUGIN-AUTHORING.md    插件制作规范（面向 Agent，自包含）
docs/REVIEW-CHECKLIST.md    审核清单（公开——作者知道会被怎么审，照着自查）
scripts/build_index.py      索引构建与校验（CI 与本地共用同一套）
.github/workflows/validate.yml
（mirror 分支）              已审内容的自动备份，兜底用，不做主分发
```

**关于 `official/` 的临时安排**：官方插件（如 `ai-quota`）的「作者仓库」本应是 Sono 主仓（官方与社区同规则上架，不走后门），但主仓公开前 raw 地址拉不到内容，所以官方插件的内容**临时**住在本仓库的 `official/` 目录里，上架条目的 `repo` 指向本仓库。主仓公开后条目改回指向主仓，`official/` 目录随之移除——届时哈希不变（同一份字节），已装用户无感知。

## 怎么提交插件

1. 照 [`docs/PLUGIN-AUTHORING.md`](docs/PLUGIN-AUTHORING.md) 做出插件，放进你自己的 GitHub 仓库，打 tag。
2. Fork 本仓库，在 `plugins/<id>.json` 写上架条目（仓库 + tag，**哈希不用写**——CI 现算）。
3. 提 PR，按 [`CONTRIBUTING.md`](CONTRIBUTING.md) 的流程走审核。

对着 [`docs/REVIEW-CHECKLIST.md`](docs/REVIEW-CHECKLIST.md) 自查一遍再提交，能省一轮往返。

## 本地跑一遍索引构建

```sh
python3 scripts/build_index.py --check                 # 校验全部条目，不写文件
python3 scripts/build_index.py                          # 生成 index.json 与 mirror/
python3 scripts/build_index.py --local-source my-plugin=../my-plugin-repo
                                                        # 条目的 tag 还没推上远端时，从本地目录读内容
```

只依赖 Python 3 标准库。`mirror/` 是构建输出（推成 `mirror` 分支的素材），不进 `main` 分支。
