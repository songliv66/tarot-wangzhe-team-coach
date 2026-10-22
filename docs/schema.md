# 离线工具输入契约

JSON 使用 UTF-8，单文件不超过 4 MiB。重复 JSON key、NaN、未知字段和未知 schema 均会拒绝。以下键名区分大小写；所有名称为非空、无首尾空格的字符串。

## 两类文件的共同字段

| 字段 | 要求 |
|---|---|
| schema_version | 必须为整数 1 |
| dataset_kind | synthetic 或 user_provided |
| description | 可选，非空说明 |
| source_note | 可选，来源及限制；不能据此认证真实性 |

synthetic 表示合成资料；user_provided 表示用户提供，仍未认证来源。工具没有“只写一个官方 URL 就认证为官方数据”的模式。

## 研究文件

共同字段之外，必须提供 games 数组，1—10000 局。每局字段如下：

| 对象 | 字段 |
|---|---|
| game | battle_id（全文件唯一）、series_id、game（系列内正整数局号）、sides、winner |
| sides | 恰好两个对象，两侧队名不同 |
| side | team、picks、bans |
| picks | 恰好五个不同英雄；同局两侧共十个英雄不能重复 |
| bans | 已明确提供的禁用数组，可以为空；不得与同局 pick 冲突或相互重复 |
| winner | 必须等于该局一侧的 team |

series_id 和 game 的组合也不得重复。`--team` 精确筛选 team 名称；被筛出的另一侧仍先接受输入校验，不能通过筛选掩盖坏数据。

结果中的一条观察是一侧在一局的完整阵容。两名英雄同队出现才计入组合；两边同时包含某两名英雄不代表它们是搭档。未给出完整禁用的材料不能推算禁用率。

## BP 文件

除共同字段外，必须提供 team、rules、lineups、branches。

| 对象 | 字段与要求 |
|---|---|
| team | name、roster |
| roster | 恰好五名本次上场队员；组织本身可以多于五人 |
| player | alias、role、heroes；alias 唯一，heroes 为 1—30 个不同英雄 |
| role | 对抗路、打野、中单、发育路、游走；五位置各一名 |
| lineups | 完整覆盖 game=1 到 best_of，依次排列 |
| lineup | game、picks、bans；可选 opponent_picks |
| picks | 对象，五个 key 恰好为 roster 的 alias，value 是该人池中的一个英雄 |
| bans | 仅已提供的当局禁用，最多30项；空数组表示没有提供，不表示正式无禁用 |
| opponent_picks | 可选，最多五个不同英雄；只能检查已提供部分 |
| branches | 0—100 个完整互斥方案，缺省内容不能省略为 null |
| branch | name、condition、lineups；name 不重复且不为 main |

rules 的五个字段都必须填写：

```json
{
  "best_of": 3,
  "own_heroes_no_repeat_across_games": true,
  "same_game_unique": true,
  "ban_scope": "provided_only",
  "complete_tournament_rules_verified": false
}
```

best_of 支持 1、3、5、7、9。own_heroes_no_repeat_across_games 可以为 true 或 false，其余三个值按上例填写；本工具只支持已提供约束，拒绝声明已认证完整赛制。单局可设 best_of=1。

每个分支提供全部局次，不仅给一处替换；工具才能核对替代是否消耗后续局英雄。分支各自从头计算，不与主方案累计。角色由队员输入决定，工具不自动证明英雄在当前版本能承担该位置。

输出含 checks_passed、plans、status=conditional_candidates、formal_match_legality=not_certified。检查通过不涵盖未提供禁抢、选取顺序、主办方特殊规则和熟练度。

完整可运行输入：[scenario.json](../examples/question-chain/scenario.json) 和 [research-games.json](../examples/question-chain/research-games.json)。
