# BP 阶段指导 · 数据接入说明

## 你想要的能力

在 **Ban/Pick / 选人** 阶段，结合：

1. **实时 draft**（谁 ban 了谁、双方已选）
2. **版本 Meta**（热门 ban/pick、对位胜率）
3. **LLM 口语化建议**（下一手禁什么 / 选什么）

## Dotabuff 能直接接吗？

| 方式 | 可行性 | 说明 |
|------|--------|------|
| **官方公开 API** | ❌ 基本没有 | Dotabuff **不对第三方免费开放**完整 stats API |
| **爬网页 HTML** | ⚠️ 不推荐 | 易违反 ToS、反爬、页面一变就挂；社区分发风险高 |
| **商业/非官方镜像** | ⚠️ 慎用 | 第三方「Dotabuff API」多半是爬虫封装，稳定性与合规都一般 |

**结论：不要把「爬 Dotabuff」作为产品主路径。**  
数据体验上类似的东西，用 **OpenDota / STRATZ** 更合适。

## 推荐架构（OpenDota + STRATZ）

```
┌──────────────┐     draft 字段      ┌─────────────┐
│ Dota GSI     │ ──────────────────► │ DraftContext│
│ (选人阶段)    │                     └──────┬──────┘
└──────────────┘                            │
                                            ▼
┌──────────────┐  段位 pick/win      ┌─────────────┐     ┌────────┐
│ OpenDota     │ ──────────────────► │             │     │        │
│ (免 Token)   │                     │ DraftAdvisor│ ──► │  LLM   │
└──────────────┘                     │  Meta 文本  │     │ 语音建议│
┌──────────────┐  段位+分路 Meta     │             │     │        │
│ STRATZ GQL   │ ──────────────────► └─────────────┘     └────────┘
│ (用户 Token) │     本地缓存 6h
└──────────────┘
```

### META_SOURCE

| 值 | 行为 |
|----|------|
| `auto`（默认） | 有 `STRATZ_API_TOKEN` → STRATZ，否则 OpenDota |
| `opendota` | 强制 OpenDota |
| `stratz` | 强制 STRATZ；失败时可回退 OpenDota |

### STRATZ 用户自备 Token（人多时的正确做法）

1. 打开 https://stratz.com/api 用 Steam 登录  
2. 复制 API Token  
3. GUI「保存 Meta 配置」或 `.env`：

```env
META_SOURCE=auto
STRATZ_API_TOKEN=你的token
STRATZ_BRACKET=high
```

- API **官方免费**，有速率限制  
- **不要把同一个 Token 写进安装包**给所有用户共享  
- 用户多了：每人自己的 Token；或向 STRATZ 申请更高档 Multi-Token  
- 请遵守 STRATZ 条款（Default Token 通常需标注 Data by STRATZ）

### 1. 实时 BP 盘面 → GSI

GSI 配置里已开启 `"draft" "1"`。  
选人阶段 `game_state` 多为 `DOTA_GAMERULES_STATE_HERO_SELECTION` / `STRATEGY_TIME`。  
DoDoClaw 解析 `payload.draft`（team2/team3 的 pick/ban）。

> 注意：天梯/征召等模式字段可能略有差异；全英雄选择也能用 Meta 指导。

### 2. 版本统计 → OpenDota（默认兜底）

| 接口 | 用途 |
|------|------|
| `GET /api/heroStats` | 段位 1–8 pick/win、职业 pro_pick / pro_ban |
| `GET /api/heroes/{id}/matchups` | 对位胜率 → 克制推荐 |

- 文档：https://docs.opendota.com/  
- **无分路聚合**（roles 是英雄标签不是 pos1–5）  
- 本地缓存：`data/meta/opendota/`

### 3. 精细 Meta → STRATZ GraphQL（已接入）

| 能力 | 说明 |
|------|------|
| GraphQL | `https://api.stratz.com/graphql` |
| Header | `Authorization: Bearer <token>` + `User-Agent: STRATZ_API` |
| 段位 | `STRATZ_BRACKET=high/mid/low/...` |
| 分路 | POSITION_1 … POSITION_5 热门英雄 |
| Token | 用户自备，见上 |

- 文档：https://stratz.com/api  
- 代码：`src/dodoclaw/meta/stratz.py`

### 4. 为何不直接「对接 Dotabuff」？

Dotabuff 的价值在 **展示与社区**，不是开放数据平台。  
对 **语音助手** 来说，真正需要的是 **结构化 pick/ban/matchup**，OpenDota 已足够支撑第一版。

若未来 Dotabuff 推出官方合作 API，再加一个 `meta.source = dotabuff` 适配器即可，上层 `DraftAdvisor` 不用改。

## 使用方式

**GUI：** 点 **「BP / Meta 指导」**，或提问：

- 「现在该 ban 谁？」  
- 「对面选了斧王我补什么？」  
- 「这版本热门阵容？」  

**环境变量：**

```env
OPENDOTA_API_KEY=   # 可选
```

**配置：** `config/settings.yaml` → `meta.enabled: true`

## 合规提示

- 仅使用 **公开 API** 与 **官方 GSI**  
- 不爬 Dotabuff、不二次贩卖其页面内容  
- Meta 是统计参考，不是胜负保证；熟练度与版本突变优先于纯数据  
