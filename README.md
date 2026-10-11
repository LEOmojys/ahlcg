# 诡镇奇谈 AHLCG（Python 实现）

《Arkham Horror: The Card Game》的规则引擎 + 网页客户端。
目前**第一章《集结》已经可以在浏览器里完整游玩**；第二、三幕与战役连贯正在开发（进度见 [STATUS.md](STATUS.md)）。

## 自动退出（不会一直占后台）

页面打开时前端每 5 秒发一次心跳（`POST /api/ping`），关闭页面时发一次 `POST /api/bye`。
服务端在页面消失后会自动退出，默认阈值 120 秒：

```bash
python -m ahlcg.web.app                 # 页面关闭后 ~8 秒自动退出（bye 立即触发，含刷新宽限）
python -m ahlcg.web.app --auto-close 300  # 想留久一点
python -m ahlcg.web.app --auto-close 0    # 完全关闭该行为，只能 Ctrl+C 停止
```

说明：

- 关页面走的是 `bye` 通道，约 8 秒后退出；这 8 秒是留给**刷新页面**的宽限期，刷新不会误杀服务。
- 心跳是兜底：浏览器崩溃等收不到 `bye` 的情况，等超过阈值才退出。阈值默认给到 120 秒，
  是为了容忍浏览器对**后台标签页定时器的节流**（可能低到每分钟一次）；页面重新可见时会立刻补一次心跳。
- 有多个标签页时，关掉其中一个不会影响其他标签页。
- 该行为只在命令行启动时生效；测试与嵌入式使用（`create_app` 默认 auto_close=0）不会自动退出。

## 启动（一条命令）

```powershell
python -m ahlcg.web.app            # 在项目根目录执行
python run.py                      # 或在任意目录执行这个
```

浏览器打开 **http://127.0.0.1:8765**

参数：`--port 9000` 换端口；`--no-images` 不下载卡图只用文字卡面。

## 出问题先跑自检

```powershell
python tools/doctor.py
```

逐项检查 Python/依赖/数据文件/卡池/五套起始牌组/机器人跑一局/剧本注册表/战役层/Web 层/
前端 HTTP 接口/前端 JS 语法，最后给结论。哪一步 FAIL 就是问题所在。

### 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| `error while attempting to bind on address ... 8765` | 端口被占用（多半是上次的服务还在跑） | 启动器现在会自动处理：已有实例在跑就直接打印网址；端口被别人占用会自动换下一个端口。也可 `--port 9000` |
| `ModuleNotFoundError: No module named 'ahlcg'` | 工作目录不对 | `cd` 到项目根目录，或用 `python run.py` |
| 页面白屏 | 前端脚本报错 | `python tools/doctor.py` 第 9 项检查前端 JS 语法 |
| 关掉终端后端口仍被占用 | 强杀外层进程时 Python 子进程可能残留 | `Get-NetTCPConnection -LocalPort 8765 -State Listen` 找 pid，再 `Stop-Process -Id <pid>` |

## 怎么玩

1. 开局选调查员（罗兰·班克斯 / 黛西·沃克 / 斯基兹·奥图尔 / 阿格尼丝·贝克 / 温迪·亚当斯）与难度。
2. 中间是调查员面板与手牌，左侧地点（可移动目标、线索、敌人），右侧幕卡/阴谋卡、混沌袋、日志。
3. **黄色边框的"选择"面板是关键**：引擎需要你决策时会出现按钮——单选点了直接提交，
   多选选好后按"确定"，可放弃的场合有"取消"按钮。
4. 手牌点一下即打出（资源不足的按钮是灰的）。
5. 本幕结束进入结算页，可"进入下一幕"（需第二幕实现后才能继续）。

## 开发

```powershell
python -m pytest -q         # 规则测试
python tools/inventory.py   # 代码盘点
python tools/doctor.py      # 端到端自检
```

架构与模块边界见 [ARCHITECTURE.md](ARCHITECTURE.md)、[SPEC.md](SPEC.md)。

## 素材来源

- 官方《规则参考》与 FAQ：`reference/pdf/rules_reference_core.txt`、`reference/pdf/faq_errata_v22.txt`
- 官方中文《狂热者之夜》战役指南：`reference/pdf/night_of_the_zealot_campaign_guide.txt`
- 卡牌数据：TTS 存档抽取 + 公开卡牌数据库（`reference/carddb.json`、`reference/arkhamdb_core.json`）

仅供个人学习与本地游玩。