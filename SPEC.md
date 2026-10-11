# 模块边界与接口规格（并行开发的契约）

多个代理同时改这个仓库。**只改自己拥有的文件**；需要别人的文件变更时，写进报告而不是动手改。
所有 Python 代码：3.12、无第三方依赖（除已有的 fastapi/uvicorn/pydantic/pillow/pypdf）、
中文用户可见文本、英文标识符、文件内不用反引号写文档字符串以外的东西。

## 目录所有权

| 目录/文件 | 所有者 | 说明 |
|---|---|---|
| `ahlcg/core/`, `ahlcg/engine/` | 引擎代理 | 规则核心，其他人只读 |
| `ahlcg/cards/core_set_player.py` | 卡牌代理 | 玩家卡行为 |
| `ahlcg/cards/core_set_encounters.py` | 剧本代理 | 遭遇卡行为 |
| `ahlcg/scenarios/` | 剧本代理 | 三幕剧本 |
| `ahlcg/campaign/` | 战役代理 | 战役层 |
| `ahlcg/web/`, `assets/` | Web 代理 | 后端 + 前端 + 卡图缓存 |
| `ahlcg/session.py`, `ahlcg/ai/`, `ahlcg/data/` | 主控 | 只由主控改 |

## 一、现有引擎接口（已实现，直接用）

```python
from ahlcg.data.pool import CardPool          # CardPool.load() -> 全部卡牌（含行为）
from ahlcg.session import GameSetup, create_game, build_chaos_bag
from ahlcg.engine.game import Game
from ahlcg.core.choices import ChoiceAnswer, PendingChoice
from ahlcg.core.enums import ChoiceKind, Skill, Trigger, CardType, Zone, Phase

game = create_game(GameSetup(pool=pool, seed=1, difficulty="standard", scenario="torch"))
game.start()                     # 生成器驱动：跑到需要玩家决策时停下
game.awaiting                    # 当前 PendingChoice（None 表示结束）
game.resolve(ChoiceAnswer(choice.id, ("选项id",)))   # 提交答案
game.state                       # GameState（见 ahlcg/engine/state.py）
game.state.pending               # 待决选择栈（栈顶 = awaiting）
game.state.log_entries           # 日志（LogEntry: text/round/phase/kind）
game.state.finished, game.state.resolution
```

### PendingChoice 的字段
`id, kind, player_id, prompt, options[ChoiceOption(id,label,detail,disabled)], min_selected,
max_selected, optional, payload`

### 行动选项 id 词表（Web 前端渲染成按钮即可，不要自己造词）
`move:<locId> | investigate | fight:<enemyId> | evade:<enemyId> | engage:<enemyId> |
play:<cardId> | activate:<cardId>:<index> | parley:<cardId> | advance_act | draw | resource |
resign | pass`

### ChoiceKind 取值
`OPTION, CARD, CARDS, ENEMY, LOCATION, INVESTIGATOR, COMMIT, ASSIGN_DAMAGE, ORDER, CONFIRM`

### 序列化
`from ahlcg.engine.state import serialize_state` 已给出基础状态 JSON；Web 层要补充玩家手牌、
支援区、威胁区等视图字段（可以自己写新的 view 函数，不要改 serialize_state 的既有键）。

## 二、战役层接口（战役代理实现，Web 代理按此调用）

```python
# ahlcg/campaign/__init__.py
@dataclass
class CampaignInvestigator:
    player_id: str          # "p1"
    name: str
    investigator_code: str  # "01001"
    deck: list[str]         # 卡牌 code 列表（含等级，代表当前牌组）
    xp_earned: int          # 累计获得
    xp_spent: int
    trauma_physical: int
    trauma_mental: int
    story_assets: list[str] # 叙事资产（如 01117 丽塔·钱德勒）
    story_weaknesses: list[str]
    killed: bool
    insane: bool
    @property
    def xp_available(self) -> int

@dataclass
class CampaignState:
    code: str                       # "night_of_the_zealot"
    difficulty: str
    seed: int | None
    scenario_index: int             # 0/1/2 = 集结/午夜面具/深渊吞噬者；3 = 三幕结束
    investigators: list[CampaignInvestigator]
    log: dict[str, list[str]]       # 战役日志：键为中文栏目名，值为中文条目
    history: list[dict]             # 每幕结算摘要
    @classmethod
    def new(cls, code, investigator_codes, difficulty, decks, seed) -> CampaignState
    def scenario_code(self) -> str | None          # 当前该玩哪一幕（"torch"/"arkham"/"tentacles"）
    def apply_resolution(self, game: Game) -> dict # 读 game.state.resolution，更新日志/XP/创伤，
                                                   # 返回摘要 dict（供 UI 展示）：见下
    def advance(self) -> None                      # 结算完推进到下一幕
    def spend_xp(self, player_id: str, purchases: list[dict]) -> list[str]  # 升级牌组
    def to_dict(self) -> dict                      # JSON（UI 展示/存档）
    @classmethod
    def from_dict(cls, data: dict) -> CampaignState

# ahlcg/campaign/game_builder.py
def build_scenario_game(campaign: CampaignState, pool: CardPool) -> Game
    """按 campaign.scenario_code() 建一局：用调查员的持久牌组、难度、创伤（开场伤害/恐惧），
       并把战役日志影响（如「你的屋子已经被焚毁」「食尸鬼祭司依然存活」）传给剧本。"""

# ahlcg/campaign/night_of_the_zealot.py
CAMPAIGN = "night_of_the_zealot"
SCENARIO_ORDER = ("torch", "arkham", "tentacles")
def resolve_summary(campaign, game) -> dict   # 中文摘要 + 经验/创伤/日志变更
```

apply_resolution 返回（UI 直接用）：
```python
{
  "scenario": "torch", "scenario_name": "第一章：集结",
  "resolution": "R1", "title": "你烧掉了自己的房子",
  "text": "……结局正文（中文）……",
  "xp_gained": 5, "trauma": {"physical": 1, "mental": 0},
  "log_changes": [{"section": "战役记录", "entry": "你的屋子已经被焚毁"}],
  "next_scenario": "arkham" | None,
  "defeated_investigators": [],
}
```

三幕的结局数值以 `reference/pdf/night_of_the_zealot_campaign_guide.txt`（官方中文指南）为准，
不要臆造：例如第一章 R1/R2 给「胜利点数 + 2 经验」、R1 领袖 1 点精神创伤；
第二章结局按发现的邪教徒/逃跑的邪教徒写日志；第三章 R1 +5、R2 +10 经验与 2/2 创伤等。

## 三、Web 接口契约（Web 代理实现）

启动：`python -m ahlcg.web.app`（默认 `http://127.0.0.1:8765`，不要占用 19387）。
后端 FastAPI，前端单页 HTML + 原生 JS（无需构建步骤），中文界面。

```
GET  /                      -> 单页界面
GET  /api/pool              -> {investigators: [{code,name,classes,stats,deck_requirement}],
                                difficulties: [...], scenarios: [...]}
POST /api/campaign/new      -> body {investigator_code, difficulty, seed?} -> {session_id, view}
GET  /api/state?session=…   -> {view}          # view 见下
POST /api/choice            -> body {session_id, choice_id, selected:[…], cancelled?:bool} -> {view}
POST /api/campaign/next     -> 结算并进入下一幕 -> {summary, view}
POST /api/campaign/spend    -> body {session_id, purchases:[{code, replace?}]} -> {view}
GET  /api/card-image/{code} -> 卡图（磁盘缓存，缺失时返回 404，前端回退到文字）
```

view = ```python
{
  "session_id": str,
  "campaign": {...},                # CampaignState.to_dict()
  "scenario": {"code","name","round","phase","resolution","finished"},
  "investigator": {"name","code","damage","horror","health","sanity","resources","clues",
                   "actions_left","location_id","skills":{...}},
  "locations": [{"id","code","name","shroud","clues","revealed","blocked","connections":[locId],
                 "enemies":[enemyId],"investigators":[playerId]}],
  "act": {"id","code","name","text","progress","required"} | None,
  "agenda": {"id","code","name","text","doom","threshold"} | None,
  "enemies": [{"id","code","name","fight","evade","damage","horror","health_remaining",
               "exhausted","engaged_with":[playerId],"location_id","traits"}],
  "play_area": [card...], "threat_area": [card...],
  "hand": [{"id","code","name","text","cost","icons","type"}],
  "discard": [card...], "deck_count": int, "encounter_deck_count": int,
  "chaos_bag": [{"type","value","label"}],
  "last_skill_test": {"skill","difficulty","skill_value","token","total","success","margin","text"} | None,
  "choice": {"id","kind","player_id","prompt","min_selected","max_selected","optional",
             "options":[{"id","label","detail","disabled"}]} | None,
  "log": [{"round","phase","kind","text"}],     # 最近 200 条，最新在前
}
```

Web 代理必须保证：`/api/choice` 提交后立刻返回新的 view；选择面板在浏览器里可点选
（单选/多选/可取消按 min_selected/max_selected/optional 决定）；界面在 1280 宽下可用。

卡图：优先从 `https://arkhamdb.com{imagesrc}` 下载（`reference/arkhamdb_core.json` 里每条记录有
`imagesrc`），缓存到 `assets/cards/{code}.png`；离线或失败时前端显示文字卡面。

## 四、剧本接口（剧本代理实现）

```python
class Scenario:
    code: str; name: str; campaign: str
    def __init__(self, pool: CardPool)
    def setup(self, game) -> None | Generator     # 允许普通函数或生成器
    # 可用基类助手（ahlcg/scenarios/base.py）
    # add_location/add_act/add_agenda/set_aside/find_card/bring_into_play/
    # build_encounter_deck/connect/install_abilities/install_token_modifier
```

剧本要读 `game.state.flags` 里战役层传入的开关（键名用中文或英文均可，但要在文件顶部注释写清楚，
供 Web/战役代理对齐）：
- `"house_burned"`: bool（你的屋子已经被焚毁）
- `"ghoul_priest_alive"`: bool（食尸鬼祭司依然存活）
- `"cultists_found"`: list[str]（我们发现的邪教徒）
- `"cultists_escaped"`: list[str]（逃跑的邪教徒）
- `"midnight_passed"`: bool（午夜已过）
- `"ritual_broken"`: bool（召唤阿布霍斯的仪式已经被破坏）
- `"investigators_sacrificed_lita"`: bool

注册进 `ahlcg/scenarios/__init__.py` 的 `_SCENARIO_CLASSES`：
`{"torch": ..., "arkham": "ahlcg.scenarios.night_of_the_zealot.the_midnight_masks:TheMidnightMasks",
  "tentacles": "ahlcg.scenarios.night_of_the_zealot.the_devourer_below:TheDevourerBelow"}`

## 五、接口增补（实现后的实际形态）

Web 端点（`ahlcg/web/app.py`，均已在测试与实机验证）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 单页前端 |
| GET | `/api/pool` | 调查员/难度/剧本列表 |
| POST | `/api/campaign/new` | `${investigator_code, difficulty, seed?, deck_codes?}`；deck_codes 提供时走自由组卡校验 |
| GET | `/api/state?session=&lang=` | 完整视图；`lang=en` 切换英文原文 |
| POST | `/api/choice` | `${session_id, choice_id, selected, cancelled}` |
| POST | `/api/campaign/next` | 结算并进入下一幕 |
| POST | `/api/campaign/spend` | 经验购买 |
| GET | `/api/campaign/upgrades?session=` | 可购买卡列表（基础包、按组卡许可过滤） |
| GET | `/api/deck-options?investigator=` | 自由组卡候选（等级 0、按许可过滤） |
| GET | `/api/card-image/{code}` | 卡图按需下载并缓存 |
| POST | `/api/ping` · `/api/bye` | 页面在线心跳 / 告别（自动退出用） |

视图新增字段：`scenario.story`（本幕开场剧情）、`act/agenda.flavor`（叙事）、
`locations[].connections/enemies/investigators`（地图）、`discard`、`deck_count`、
`victory_display`、`investigator.text/code`（立绘与卡面）。

## 五、验收

每个代理交付：(1) 代码；(2) 自己的 pytest 文件；(3) `python -m pytest -q` 全绿（不得让既有 112 个测试变红）；
(4) 简短报告：做了什么、故意没做什么及原因、需要别人配合的接口变更。
