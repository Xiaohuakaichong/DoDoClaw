# 知识库：英雄机制 + 官方补丁

## 做什么

在 GSI / Meta 之外，为 LLM 提供 **可检索的事实材料**：

| 类型 | 数据源 | 内容 |
|------|--------|------|
| 英雄机制 | [OpenDota constants](https://api.opendota.com/api/constants/heroes) + abilities | 定位、属性、技能描述与数值 |
| 官方补丁 | [Valve datafeed](https://www.dota2.com/datafeed/patchnoteslist) | 最近 N 个版本全局/物品/英雄改动 |

**不是**向量云服务；本地 JSON 索引 + 关键词检索，零额外依赖。

## 流程

```
首次提问 / knowledge-sync
        │
        ▼
抓取 OpenDota + Valve ──► data/knowledge/index.json
        │
提问时 ──► 识别问题里的英雄（中文名/外号）+ 当前 GSI 英雄 ──► 检索 Top-K ──► 拼进 LLM 上下文
```

### 检索怎么选文档

1. **问题里提到的英雄优先**：`dodoclaw/names.py` 用 `data/hero_aliases.json`（中文名、英文名、
   社区外号如「敌法 / 蓝猫 / 小Y / SF」）在问题里找英雄。按别名表的要求只做"最长匹配"，
   不做松散子串匹配（「兽王」不会再被「兽」命中；一个字的外号如「陈」「凯」在句子里跳过）。
2. **每个英雄强制带上**：机制文档 + 最新一条补丁改动；然后才是自己当前的英雄。
3. **其余按关键词得分补满 Top-K**：中文切成二字词（「削弱了什么」→ 削弱 / 弱了 / 了什 / 什么），
   不再是固定 1–4 字切块；完全不相关（0 分）的文档不会被硬塞进来。
4. **字数预算平分**：多篇文档时每篇至少 600 字，避免第一篇很长的英雄文档把 `max_chars` 吃光。
5. 文档分词结果按 (id, 文本) 缓存，单次检索从 ~30ms 降到个位数毫秒。

## 命令

```powershell
# 强制同步（需能访问 OpenDota 与 dota2.com）
python -m dodoclaw knowledge-sync

# 查看统计
python -m dodoclaw knowledge-stats
```

## 配置 `config/settings.yaml`

```yaml
knowledge:
  enabled: true
  language: "schinese"   # 或 english
  patch_last_n: 3
  ttl_sec: 86400
  top_k: 6
  max_chars: 2800
```

## 代码

- `knowledge/heroes.py` — 英雄机制文档构建  
- `knowledge/patches.py` — 补丁抓取与切分  
- `knowledge/retriever.py` — 检索  
- `knowledge/base.py` — 同步/缓存/对外 API  

## 局限

- 技能描述语言取决于 OpenDota constants（多为英文 desc）  
- 补丁中文取决于 Valve `language=schinese` 是否完整  
- 非语义向量：冷门问法可能检索不全  
- 一个字的英雄名/外号（陈、凯、兽）在句子里不识别，可用全名或别的叫法  
- 出装推荐仍主要依赖 Meta + LLM，本库偏 **机制与补丁事实**  
