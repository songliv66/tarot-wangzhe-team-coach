# 配套工具

工具使用 Python 3.9+ 标准库。以下命令从仓库根目录执行；输出 JSON 到终端，演示和采集的写入目录必须是新目录。程序不会搜索你的家目录、读取私人游戏账户或调用模型。

从自己的资料创建输入时，先看[完整字段与约束契约](schema.md)，不必先阅读脚本实现。

## 离线同队组合统计

```sh
python3 scripts/coachkit.py analyze examples/question-chain/research-games.json --team 纸鸢队
```

输入为 schema_version=1 的 JSON，dataset_kind 明确为 synthetic 或 user_provided。每局记录 battle_id、series_id、game、winner，以及两边的 team、五个 picks 和 bans。完整字段以 [可运行研究样例](../examples/question-chain/research-games.json) 为准。

工具先验证所有局，再按阵营统计。每局两边须为不同队伍，十个 pick 不重复；ban 不算搭档，也不能与 pick 冲突。battle_id 和同系列局号不得重复。指定队名后，出现数和胜负仅来自该队的阵容。未知字段、无效胜方、不完整阵容和重复记录会失败，不能靠静默丢行得到漂亮结果。

`user_provided` 仅表示用户提供，不能转换为“官方认证”。真实接口响应须人工核对字段并归一化，保存原始快照和变换说明；当前读取器不自动完成这一步。

## 条件 BP 检查

```sh
python3 scripts/coachkit.py check-bp examples/question-chain/scenario.json
```

输入列出五位置队员、各自英雄池、明确的规则、逐局完整 picks，以及可选的完整替代分支。它检验位置覆盖、英雄池、同局重复、提供的禁用或对手已选，以及已声明的己方跨局重复约束。

例子有三局主方案和一套互斥的禁用分支。每个分支独立计算全局消耗；不能把分支当作主方案额外打的三局。返回 conditional_candidates，完整赛事合法性为 not_certified。空禁用列表表示输入未提供，不能据此认定没有禁用。规则未知或超出本工具支持范围时，需要按主办方资料人工检查。

## 训练时段

```sh
python3 scripts/coachkit.py train --minutes 90
python3 scripts/coachkit.py train --minutes 60
```

支持 15—480 分钟的整数预算，五阶段时长合计等于输入。它只分配时间，不自动判断战术，也不保证某时长内完成几局比赛。目标与指标由 Skill 对话结合真实资料选择。

## 实验性腾讯网页接口读取

只有显式执行以下命令才联网，每次只发出一个请求，不自动翻页或重试。先读取赛事列表核对名称与日期，再给具体 ID；不要按 ID 大小猜赛季。

```sh
python3 scripts/fetch_official.py leagues --output-dir work-leagues
python3 scripts/fetch_official.py heroes --league-id 123 --output-dir work-heroes
python3 scripts/fetch_official.py matches --league-id 123 --output-dir work-matches
python3 scripts/fetch_official.py battles --match-id 123 --output-dir work-battles
python3 scripts/fetch_official.py battle --battle-id 123 --output-dir work-battle
```

123 是占位示例，不是已确认的有效赛事 ID。输出目录的父目录须已存在；目录本身须不存在。也可不提供 output-dir，仅向标准输出写结果。

固定请求域为 https://prod.comp.smoba.qq.com，端点为 leaguesite 下的 leagues/open、league/hero/settle_list/open、matches/open、match/battles/open、battle/open。禁止重定向与任意 URL；单次 socket／请求超时为 8 秒、响应上限 4 MiB。socket 超时不是整次运行的绝对墙钟上限。

成功时保存 response.json 原始字节与 provenance.json，记录 URL、读取时间、字节数、SHA-256 和未知版本。哈希证明字节一致，不证明内容或来源得到腾讯签名认证。失败时退出码为 2，不落盘一个伪装成功的快照，不用旧文件替代。

这些是实验性网页接口，字段和开放状态可能变化。当前协议只验证响应外壳，不能声称已经核验所有赛事业务字段。数据、视频和规则的使用权仍取决于来源条款。

## 完整 demo

```sh
python3 scripts/run_demo.py --out demo-output
```

该命令不联网。它运行统计、BP 和 90／60 分钟时段检查，把预写五阶段示例及实际工具结果生成 HTML、Markdown、JSON 和哈希清单。示例输入仍是合成数据，生成器并未实时调用模型。
