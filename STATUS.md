# 项目现状 STATUS

## 一句话

《诡镇奇谈 AHLCG》的 Python 规则引擎已经能**自动完整跑完第一章「集结」**：混沌袋、技能检定、
四个阶段、遭遇牌、敌人、幕/阴谋推进、结局判定全部打通，112 个测试全绿。网页界面和战役层还没做。

## 已经能跑的东西

```powershell
python -m pytest -q          # 112 passed
python tools/inventory.py    # 代码盘点
```

机器人自动对局（可用作回归测试与后续 AI 基线）：

```python
from ahlcg.data.pool import CardPool
from ahlcg.session import GameSetup, create_game
from ahlcg.ai import robot

game = create_game(GameSetup(pool=CardPool.load(), seed=11))
print(robot.play(game))      # -> {'finished': True, 'resolution': 'R3', 'rounds': ...}
```

## 模块地图

| 目录 | 内容 |
|---|---|
| `ahlcg/core/` | 卡牌定义与实例、枚举、选择（PendingChoice）、事件时机、随机数、序列化 |
| `ahlcg/engine/` | 生成器驱动的流程、四个阶段、技能检定、行动、伤害/线索/毁灭、敌人行为 |
| `ahlcg/cards/` | 卡牌行为：core_set_encounters.py（遭遇卡）、core_set_player.py（29 张玩家卡） |
| `ahlcg/scenarios/` | 剧本框架 + night_of_the_zealot/the_gathering.py |
| `ahlcg/data/` | ArkhamDB → CardDef 装载器、卡池、牌组 |
| `ahlcg/ai/` | 机器人策略（测试与自动对局用） |
| `ahlcg/session.py` | 组装一局游戏：卡池、牌组、混沌袋、剧本 |
| `tools/` | 素材管线（TTS 存档 / PDF / ArkhamDB）与盘点脚本 |
| `reference/` | 抽取出来的数据：官方规则参考全文、FAQ、中文战役指南、卡牌数据库 |

## 核心设计

1. **生成器驱动**：流程写成生成器，需要决策时 `yield` 一个 `PendingChoice`，答案 `send` 回来。
   卡牌效果因此可以写成顺序代码（`yield from ctx.ask_yes_no(...)`），不必为每张卡写状态机。
2. **选择驱动**：测试、机器人、Web 前端消费同一套选择，规则只有一份实现。
3. **数据与行为分离**：`CardDef` 是纯数据（来自公开卡牌数据库），能力挂在 `ahlcg/cards/` 的注册表里。
4. **决定论**：所有随机经 `core/rng.Rng`，可存可取；任何一局都能用「种子 + 决策序列」复现。
5. **以官方规则为准**：`reference/pdf/rules_reference_core.txt` 是权威依据。已据此修正：第一轮
   **跳过整个神话阶段**；敌人阶段 3.2 先猎手移动、3.3 再结算交战敌人攻击；敌人攻击后消耗；
   维持阶段 4.3 让所有已消耗卡牌就绪（含敌人）。（`yield` 只用于让出选择，见 `Game._pump`。）

## 素材包给了什么

`C:\Users\假烟桑··\Desktop\一步到胃`（989 文件 / 12 GB，TTS mod + 卡图 + PDF）：

- **官方《规则参考》全文**（32 页）+ **FAQ/勘误 v2.2**（26 页）→ 已转文本，规则争议的最终依据
- **官方中文《狂热者之夜》战役指南**（8 页）→ 三幕设置、四档混沌袋、结局与经验
- **4759 张带官方编号的卡牌结构化数据**（类型/职业/费用/等级/特性/图标/胜利点）→ `reference/carddb.json`
- 918 张卡图（多为 10x7 卡表，可用 Pillow 按 CardID 裁成单卡 → 网页版卡图来源）
- 公开卡牌数据库补全了 TTS 缺失的数值（敌人战力/闪避/生命、地点遮蔽、调查员属性、规则文本）

## 已知缺口

### 引擎层
- **常量修正钩子**：Magnifying Glass / Holy Rosary 这类「+1 智力」的常驻加成没地方挂
  （子代理因此故意没有实现它们，而不是写死代码）。
- **检定中窗口**：Physical Training / Arcane Studies 这类「检定中花资源」的 [fast] 能力无法表达；
  已投入卡也没有「检定成功后」的时机。
- **技能替换**：Shrivelling「用意志代替战斗力」未支持。
- **取消标记**：Dodge / Ward of Protection 会设置取消标记，但引擎还没消费它。
- **额外行动**：Leo De Luca 的「每回合多 1 行动」未建模。
- **多人规则**：多调查员的数据结构已就位（`players` 列表、玩家顺序），但未测试。
- **借机攻击**已实现；**报复**已实现；**猎手**已实现；**永久/快速/盟友槽位**尚未处理。

### 内容层
- 第二章「午夜面具」、第三章「深渊吞噬者」的剧本、遭遇卡效果、午夜面具牌组尚未实现。
- 战役层（战役日志、XP、创伤、牌组升级、跨场景延续）未实现。
- 玩家卡只实现了 29 张（基础包约 120 张）。

### 界面层
- Web 后端（FastAPI + WebSocket）与前端棋盘界面未实现。`serialize_state()` 已备好数据出口。

## 下一步

1. Web 后端 + 前端（棋盘/手牌/混沌袋/日志/选择面板），卡图用 CardID 裁切卡表生成
2. 战役层（日志/XP/创伤）与第二章、第三章
3. 补齐基础包玩家卡；先把「常量修正钩子」和「检定中窗口」两个引擎短板补上

---

# 交接备忘（下一轮从这里开始）

## 当前可验证的事实

- `python -m pytest -q` → **119 passed**（引擎/检定/卡牌/剧本/组卡全绿）
- 机器人可自动打完第一章：`create_game(GameSetup(pool=CardPool.load(), seed=11)) + robot.play(game)`
- 组卡器可用：`build_starter_deck(pool, code)` 生成五名调查员的合法 30 张牌组（`validate_deck` 通过），
  `ROLAND_STARTER` 常量已恢复
- Web 后端已就绪：`ahlcg/web/app.py` 有 `create_app(pool, image_store)` 与 `main()`（`python -m ahlcg.web.app`），
  `GET /api/pool` 返回 200 + 五名调查员数据
- 战役层文件存在且可导入：`ahlcg/campaign/{__init__,night_of_the_zealot,game_builder}.py`

## 立刻要补的三件事

1. **前端页面缺失**：`GET /` 报 `ahlcg/web/static/index.html does not exist`。
   只差一个单页前端（原生 JS，接口契约见 SPEC.md 第三节的 view 字段）。
2. **`POST /api/campaign/new` 报错**：需要按堆栈修 `ahlcg/web/sessions.py` 与 `ahlcg/campaign` 的对接
   （战役代理被中断，接线可能没写完）。
3. **第二、三幕未实现**：`ahlcg/scenarios/__init__.py` 只注册了 `torch`。

## 重要教训：不要让子代理去读大数据文件

多次代理失败都发生在要求它们先读 `reference/arkhamdb_core.json`（2.9 MB）或
`reference/pdf/rules_reference_core.txt`（140 KB）之后——上下文当场被吃光，任务未产出。
已经准备好**小份任务数据**，后续派发只能让它们读这些：

- `reference/notz_scenario_data.json`（45 KB）：三幕各自的遭遇设置与卡牌文本/数值
- `reference/rules_digest.md`（13 KB）：只摘录实现需要的规则段落（阶段流程、借机攻击、猎手、创伤、经验…）
- `SPEC.md`（10 KB）：模块边界与接口契约

派发任务时：一个代理只做一个文件级的小目标（参考成功案例：29 张玩家卡那个代理只写了一对文件），
禁止它读上面列出的两个大文件，把需要的卡牌/规则原文贴在提示里或让它读上面的小文件。

## 剩下的工作清单

- 引擎钩子：常量修正、检定中窗口、投入卡结果时机、槽位、起手重抽
- 第二幕《午夜面具》、第三幕《深渊吞噬者》（数据已在 notz_scenario_data.json）
- 战役层接线与三幕连贯（XP/创伤/日志/结局正文）
- 基础包玩家卡从 29 张补到完整卡池
- 前端单页 + 卡图（ArkhamDB imagesrc 下载缓存到 assets/cards/）
- README 上手文档，一条命令启动

---

# 第 1 轮目标轮进展（可开箱即玩）

## 已达成：一条命令启动 + 浏览器里能玩第一章

```powershell
python -m ahlcg.web.app            # 浏览器打开 http://127.0.0.1:8765
python -m ahlcg.web.app --no-images --port 8765
```

实测（真实 HTTP，不是测试客户端）：

| 请求 | 结果 |
|---|---|
| `GET /` | 200，17 KB 中文单页界面（含选择面板、开始按钮） |
| `GET /api/pool` | 200，罗兰·班克斯 / 黛西·沃克 / 斯基兹·奥图尔 / 阿格尼丝·贝克 / 温迪·亚当斯，四档难度 |
| `POST /api/campaign/new` | 200，建局并发出 5 张起始手牌，幕「Trapped」、阴谋「What's Going On?!」 |
| `POST /api/choice` | 200，行动 → 投入卡窗口 → 检定（混沌标记/成功失败）→ 线索与行动数推进，循环可用 |

本轮修掉的两个中断遗留 bug：
- `ahlcg/web/sessions.py`: `create()` 调用了不存在的 `self._campaign_loader()`（应为 `self._loader()`），
  这曾让 `POST /api/campaign/new` 返回 500。
- `ahlcg/data/deck.py`: 我重写时删掉了 `ROLAND_STARTER`，导致 `ahlcg/web/decks.py` 导入失败；
  已恢复并通过 `validate_deck`（LEGAL）。

新增/补全的文件：
- `ahlcg/web/static/index.html`（单文件前端：开局界面、地点/调查员/手牌/幕与阴谋/混沌袋/日志、
  选择面板（单选/多选/可取消）、检定结果横幅、结算页与「进入下一幕」、卡图带失败回退）
- `tools/make_task_data.py` → `reference/notz_scenario_data.json`（45 KB）与 `reference/rules_digest.md`（13 KB）

## 子代理结论：本环境下不可靠，改为主控自己做

9 个子代理里只有 1 个成功（任务最窄、只写两个文件的那个）。之后无论提示写得多小都会失败，
且多数不留任何文件。原因基本确认是上下文被大数据文件吃光，但缩小提示后仍然失败，说明派发本身
在当前环境不稳定。后续一律由主控自己小步实现，不再派发。

## 距离目标还差

1. **第二、三幕未实现**（`GET /api/pool` 的 scenarios 目前只有 `torch`）：数据已备好，
   见 `reference/notz_scenario_data.json`（arkham 30 张 / tentacles 37 张卡，含文本与数值）。
2. **战役连贯性未验证**：`/api/campaign/next`、XP 升级、创伤跨场景——要等第二幕存在后一起验。
3. **引擎钩子**（常量修正、检定中窗口、投入卡结果时机、槽位、起手重抽）未做。
4. **玩家卡 29/约 120 张**；卡图默认关闭（`--no-images`），需要时再开。
5. **README 上手文档**。

---

# 第 5 轮进展：第二幕完成，战役连贯性打通

```
python -m pytest -q   ->  128 passed
```

## 新增

- **第二章《午夜面具》可玩**（`ahlcg/scenarios/night_of_the_zealot/the_midnight_masks.py`）：
  市中心/南区各随机 1 张 + 其余 7 个地点的阿卡姆地图；幕卡 01123「揭发阴谋」；
  阴谋卡 01121a「掠食者还是猎物？」/ 01122「时间不多了」；
  **独立的邪教徒牌库**（5 名具名邪教徒，与遭遇牌堆分开，靠幕卡的"每人 2 线索"行动抽取）；
  场景参考卡 01120 的符号修正与附加效果；屋子被焚毁时改为从河滨小镇出发；放弃(Resign)可用；
  结局 R1（幕卡推进）/ R2（午夜已过）以及把「我们发现的邪教徒 / 逃跑的邪教徒」写进 `state.flags`
- 遭遇卡行为（`ahlcg/cards/encounters_midnight.py`）：Hunting Shadow、False Lead（含涌潮）、
  Mysterious Chanting、On Wings of Darkness、Locked Door（撬门/撬锁）、墓地进场检定、
  Acolyte/Wizard 的毁灭、Ruth Turner 被闪避入胜利点、三名邪教徒的谈判入胜利点
- **连贯性集成测试**（`tests/test_campaign_continuity.py`）：第一章打完 → `apply_resolution` 结算
  → `advance` → 第二章建立起并可打完 → 推进到第三章；创伤跨场景生效；存档 JSON 往返一致

## 修掉的两个真实规则错误

1. **阴谋推进的比较对象错了**：规则参考 1.3 要求比较**场上毁灭标记总数**（含敌人与其他卡上的），
   原实现只看阴谋卡自身——导致 Acolyte / 神秘吟唱 / 巫师放的毁灭完全白费。已改。
2. **推进阴谋时应清空所有毁灭标记**（原文 "remove all doom from play"），原实现把剩余毁灭"结转"给下一张阴谋卡。已改。

另外补了三个引擎小坑：`Spawn - St. Mary's Hospital` 这类含句点的刷怪地点解析、
`Spawn - Any empty location`（刷到没有调查员与敌人的地点且不交战）、
以及幕卡「花费线索抽取邪教徒牌库」这个新行动。

## 现在的整体状态

| 项 | 状态 |
|---|---|
| 第一章《集结》 | ✅ 可玩 |
| 第二章《午夜面具》 | ✅ 可玩（本轮新增） |
| 第三章《深渊吞噬者》 | ❌ 未实现（`build_scenario_game` 会给出明确中文错误：还没有实现） |
| 战役层（日志/XP/创伤/存档） | ✅ 已通过连贯性测试 |
| 网页界面 | ✅ 可玩第一章与第二章；"进入下一幕"接战役层 |
| 五名调查员起始牌组 | ✅ 合法性测试通过 |
| 玩家卡池 | ⚠️ 29 张（基础包约 120 张） |
| 引擎钩子（常量修正/检定中窗口/槽位/重抽） | ❌ 未做 |
| 卡图 | ⚠️ 默认关闭 |

## 下一轮第一件事

第三章《深渊吞噬者》——数据已备好（`reference/notz_scenario_data.json` 的 `tentacles`，37 张），
做完这一项，"浏览器里连续玩完三幕"这条验收线就只剩界面细节了。

---

# 第 6 轮进展：第三章完成，三幕全程打通 🎉

```
python -m pytest -q   ->  135 passed
```

**验收主线的自动化证据**（`tests/test_campaign_continuity.py::test_full_campaign_plays_all_three_scenarios`）：
`CampaignState.new` 起一局 → 依次建立并打完 `torch → arkham → tentacles` → 每一幕都 `apply_resolution` 结算
→ 最终 `scenario_index == 3`、`scenario_code() is None`、战役日志与 3 条历史记录齐备。

## 新增

- **第三章《深渊吞噬者》可玩**（`ahlcg/scenarios/night_of_the_zealot/the_devourer_below.py`）：
  主干道 + 随机 4 张阿卡姆树林（其余 2 张移除）；幕卡 01146/01147/01148；
  阴谋卡 01143/01144/01145；四种代理人组随机取 1 组；阿布霍斯与仪式所先放置一旁；
  读取战役日志开关（逃跑的邪教徒 → 阴谋卡毁灭、午夜已过 → 随机弃 2 张手牌、
  食尸鬼祭司存活 → 洗入遭遇牌堆）；混沌袋额外加入 1 个远古之物指示物；
  结局 R1（干扰仪式）/ R2（击败阿布霍斯）/ R3（献祭丽塔）。
- **遭遇卡行为**（`ahlcg/cards/encounters_devourer.py`）：阿布霍斯的愤怒（逐点抉择）、
  黄印、力量的诱惑、梦境（威胁区 + 可挣脱）、拜亚基/伊斯观察者/黑暗幼体/山羊幼崽/深潜者、
  仪式所补线索、树林指定检定技能（意志/敏捷/战斗代替智力）、离开地点需检定。
- **通用地点行动机制**（引擎）：地点可用 `meta["location_actions"]` 声明行动，
  卡牌模块用 `register_location_action` 注册处理函数，支持"每回合一次/每局一次"限制，
  威胁区卡牌的 [action] 能力也能被发动。引擎能力补齐：按人数加生命（阿布霍斯 +4/人）、
  按敌人个体的战力/闪避/伤害修正、阴谋卡耗尽的抑制开关。

## 目前的整体状态

| 项 | 状态 |
|---|---|
| 三幕剧本 | ✅ 全部可玩 |
| 战役连贯（日志/XP/创伤/存档/结算） | ✅ 三幕全程自动化测试通过 |
| 网页界面 | ✅ 一条命令启动，三幕都能玩；补了"战役结束"界面 |
| 五名调查员起始牌组 | ✅ |
| 玩家卡池 | ⚠️ 29 / 约 120 张 |
| 引擎钩子（常量修正/检定中窗口/投入卡时机/槽位/起手重抽） | ❌ 未做 |
| 《午夜面具》8 个地点的行动按钮 | ❌ 机制已就绪，尚未接线 |
| 卡图 | ⚠️ 默认关闭（`--no-images`） |

## 下一轮

1. 把《午夜面具》的 8 个地点行动接上（机制已存在，只是登记 `location_actions` + 处理函数）
2. 玩家卡池从 29 张补到基础包完整卡池，并顺手补上引擎钩子（常量修正、检定中窗口、槽位、重抽）
3. 浏览器里的场景间 XP 升级界面

---

# 第 7 轮进展：引擎钩子补齐，之前"故意没实现"的 9 张卡全部落地

```
python -m pytest -q   ->  154 passed
```

这一轮解决的正是**当前可玩性最痛的地方**：五名调查员的起始牌组里原本有不少卡是"有卡面、没效果"
（放大镜不加智力、体能训练用不了、Vicious Blow 不加伤害……），因为引擎缺少相应机制。

## 新增的引擎钩子（都是声明式数据，卡牌模块只填 meta / 注册 Ability）

| 钩子 | 卡牌怎么用 | 已经用上的卡 |
|---|---|---|
| 常量修正（含减值） | `meta["constant"] = [{"skill": "intellect", "amount": 1, "kind": ["investigate"]}]`、`meta["penalty"]` | 放大镜、圣玫瑰念珠、巡警、米兰博士、梦回拉莱耶 |
| 检定中窗口 | `meta["in_test"] = {"skills": [...], "cost": 1, "bonus": 1}`（可重复使用，直到你不再付费） | 体能训练、奥术研究 |
| 投入卡的结果时机 | `Ability(trigger=ON_SUCCESS/ON_FAIL)`，事件里带上 test/result，可回写 `test.meta` | Vicious Blow（+1 伤害）、Deduction（+1 线索）、Opportunist（成功 3+ 退回手牌） |
| 技能替换与充能 | `meta["attack"] = {"skill": "willpower", "damage": 2, "uses": "charge"}`、`meta["uses"]` | 邪咒（用意志攻击、4 充能、+1 意志 +1 伤害） |
| 额外行动 | `meta["extra_action"] = 1` | 里奥·德卢卡 |

## 顺带

- 没有充能/弹药的武器不再出现在攻击选项里（避免选到用不了的武器）
- 那个"故意没实现"的守护测试改成了**正向断言**：这些卡现在必须有对应钩子（旧断言已经过期）

## 整体状态

| 项 | 状态 |
|---|---|
| 三幕剧本 + 战役连贯 | ✅ 三幕全程自动化测试通过 |
| 网页界面 | ✅ 一条命令启动；三幕都能玩 |
| 引擎钩子 | ✅ 常量 / 检定中窗口 / 投入卡时机 / 技能替换 / 额外行动 |
| 玩家卡池 | ⚠️ 38 / 约 120 张 |
| 仍是缺口 | 支援卡槽位校验、起手重抽（mulligan）、《午夜面具》8 个地点行动、浏览器里的 XP 升级界面、卡图 |

---

# 第 8 轮：起手重抽 + 槽位校验，并修掉一个我自己引入的真 bug

python -m pytest -q -> 160 passed

- 新增：起手重抽（开局可换任意张手牌，换掉的洗回牌库）；支援卡槽位（手/奥术 2 格，
  盟友/饰品/身体/塔罗各 1 格，超限必须先弃卡）；双手武器 Hand x2 正确占 2 格。
  两者默认关闭（无头驱动器需要 start() 后直接看到行动选择），在网页与战役路径中开启。
- 修掉的真 bug：Game.start() 的语义。上一轮为修“剧本被设置两遍”把它改成绝对幂等，
  破坏了“显式传入流程”的用法（测试驱动器用它跑单个行动/单张卡效果），7 个既有测试变红。
  正确语义：显式传 flow 时总是替换驱动器；无参调用才幂等。
- 定位方法：先把 .45 Automatic 的基本攻击在驱动器之外独立复现（确认引擎正确），
  再读驱动器实现，看到它调用 game.start(self.flow)，问题即明确。
- 测试策略修正：机器人可能在第一幕就被困死（R3 是规则的合法结果），
  因此连贯性测试改为规则感知：三幕各自可建立/打完/结算、顺序恒定、
  调查员被杀害时战役层必须明确拒绝继续（CampaignGameError），存活时才验证创伤延续。

## 仍是缺口

- 玩家卡池 38 / 约 120 张
- 《午夜面具》8 个地点行动未接线（机制已就绪）
- 浏览器里的场景间 XP 升级界面
- 卡图默认关闭（--no-images）

---

# 第 16 轮：基础包玩家卡池 100/100，并完成端到端验收

python -m pytest -q -> 206 passed
python tools/doctor.py -> 9 组全通过

- 最后两张卡补齐：The Necronomicon（进威胁区 + 3 恐惧，你控制的典籍文本视为空白）、
  Wendy's Amulet（可从弃牌堆打出最上面的事件 + 打出事件后弃牌库顶）。
- 顺带修复一个真实功能缺口：**玩家弱点被抽到时从未结算它的启示**（此前只有测试直接调用过
  resolve）。现在 draw_cards 会在抽到弱点时立即结算，五个基础弱点与调查员弱点才真正生效。
- 空白化机制扩展到主动能力列表（此前只作用于触发式能力，被空白化的典籍仍能被发动）。

## 端到端验收

python tools/run_campaign.py —— 机器人连续打完三幕并打印战役结局：
  第 1 幕 集结 -> R3；第 2 幕 午夜面具 -> 战败；第 3 幕 深渊吞噬者 -> 战败；
  战役结束，日志记录了各幕结局与获得的故事资产（黛西获得丽塔），存活 4/5。

注意：机器人只是启发式 AI，三幕都打输了（R3/战败都是规则的合法结局）。
引擎与战役层走完了全部三幕并给出结局，这一点是确定的；胜负取决于玩家水平。

## 已知取舍

- 卡图默认关闭（--no-images）；接口 GET /api/card-image/{code} 已就绪。
- 战役层的 scenario_code 是方法而非属性（与相邻的 scenario_order 属性风格不一致），
  全仓库都按方法调用，已确认无缺陷，但容易被误用。

---

# 收尾状态（最终）

本文档前半部分按轮次记录了开发过程；这里汇总最终状态。

- **测试**：220+ 全部通过（`python -m pytest -q`）；`tools/doctor.py` 九组自检全过
- **卡池**：基础包玩家卡 100/100 实现卡面效果（含 L1–L5、基础弱点、修订版印次回退）
- **已完成**：三幕战役连贯、场景间 XP 升级、自由组卡编辑器、断点恢复（日志重放）、
  可视化地点地图（防重叠）、卡图按需下载、全中文卡面与叙事（开场/结局/幕卡 flavor）、
  点击查看任意卡牌详情、页面自动退出
- **已知未做**：多人同局、霰弹枪失败分支（单人无从触发）、个别边缘条款
- **注意**：第 9–15 轮的细节报告在开发会话中，本文档未逐轮回填；以本节与 git 提交史为准
