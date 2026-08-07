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
提问时 ──► 按问题 + 当前 GSI 英雄检索 Top-K ──► 拼进 LLM 上下文
```

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
- 出装推荐仍主要依赖 Meta + LLM，本库偏 **机制与补丁事实**  
