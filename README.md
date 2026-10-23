# DoDoClaw 🦀

**Dota 2 语音助手 / 教练** — 桌面 App + Valve **GSI** 读局 + 语音/文字问答 + TTS + 定时提醒。

适合社区分发：打包成 **便携 zip / 双击 exe**，用户无需安装 Python。

| 模块 | 说明 |
|------|------|
| **桌面 App** | CustomTkinter GUI：启动服务、装 GSI、填 API Key、聊天提问 |
| **GSI** | 本地 HTTP 接收 Dota 2 推送（血量、金钱、时间、技能、物品等） |
| **Coach** | 基于 xAI（Grok）结合局势回答「现在该出什么」等问题 |
| **STT / TTS** | 语音识别与播报（默认 mock；可换 Whisper / Edge TTS） |
| **Reminders** | 神符刷新、买活可用、残血等事件提醒 |

---

## 社区用户：用打包版（推荐）

1. 下载 `DoDoClaw-win64.zip` 并解压  
2. 双击 **`DoDoClaw.exe`**  
3. 填写 [xAI API Key](https://console.x.ai) → **保存 Key**  
4. 点 **安装 Dota GSI 配置** → **完全重启 Dota 2**  
5. 点 **启动服务** → 进对局，在窗口里提问  

开发者本地打社区包：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1
# 产物: dist\DoDoClaw\DoDoClaw.exe  与  dist\DoDoClaw-win64.zip
```

详见 [packaging/README.md](packaging/README.md)。

---

## 开发者：源码运行

**环境：** Windows + Python **3.11+**、Dota 2、（可选）xAI API Key

```powershell
cd D:\Project\DoDoClaw
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[app]"

copy .env.example .env
# 编辑 .env，填入 XAI_API_KEY=...

# 桌面 App（默认）
python -m dodoclaw gui

# 或终端模式
python -m dodoclaw cli
```

### CLI 命令

| 命令 | 作用 |
|------|------|
| `python -m dodoclaw` / `gui` | 桌面 App |
| `python -m dodoclaw cli` | 终端交互 |
| `python -m dodoclaw install-gsi` | 安装 GSI 配置 |
| `python -m dodoclaw health` | 检查 GSI /health |

### 终端交互

| 输入 | 作用 |
|------|------|
| 直接打字提问 | 结合当前局势问教练 |
| `/listen` | 走 STT |
| `/status` | 打印 GSI 摘要 |
| `/quit` | 退出 |

### 可选语音依赖

```powershell
pip install -e ".[speech]"
```

```env
STT_BACKEND=whisper
TTS_BACKEND=edge
```

---

## 项目结构

```
DoDoClaw/
├── config/                 # settings + GSI cfg 模板
├── packaging/              # PyInstaller spec / 入口
├── scripts/
│   ├── build_app.ps1       # 一键打 exe + zip
│   └── install_gsi.ps1
├── src/dodoclaw/
│   ├── gui/                # 桌面 App
│   ├── service.py          # 核心服务（GUI/CLI 共用）
│   ├── main.py             # CLI 入口
│   ├── gsi/  coach/  voice/  reminders/
├── tests/
└── pyproject.toml
```

## GSI 说明

1. 配置文件必须放在：

   `...\dota 2 beta\game\dota\cfg\gamestate_integration\gamestate_integration_dodoclaw.cfg`

2. **完全退出并重启 Dota 2**（仅重开一局不够时，请杀进程再开）。
3. 本地监听默认：`http://127.0.0.1:3000/`，token：`dodoclaw_secret`（与 `.env` / cfg 保持一致）。
4. 仅 **本机对局 / 观战** 相关数据；不替代 replay 解析或第三方 overlay API。

**原理与是否「外挂」：** 见 [docs/GSI_AND_SAFETY.md](docs/GSI_AND_SAFETY.md)。  
简要：Valve **官方 GSI**，客户端主动 POST 到 `127.0.0.1`，**无注入、不改内存**；本工具做教练建议，不自动操作游戏。

## 知识库（英雄机制 + 官方补丁）

教练回答会检索本地知识库（首次提问可自动同步，也可手动）：

```powershell
python -m dodoclaw knowledge-sync
python -m dodoclaw knowledge-stats
```

- 英雄技能/机制：OpenDota constants  
- 补丁改动：Valve 官方 patchnotes（最近 N 个版本）  
- 详见 [docs/KNOWLEDGE.md](docs/KNOWLEDGE.md)

## BP / 选人指导

- **实时盘面**：GSI `draft` 字段（双方 ban/pick）  
- **版本 Meta**：
  - **OpenDota**（默认兜底，免 Token，有段位 1–8）
  - **STRATZ**（用户自备 Token，段位 + **分路** Meta）  
- `META_SOURCE=auto`：填了 `STRATZ_API_TOKEN` 就用 STRATZ，否则 OpenDota  
- GUI：**BP Meta 数据源** + **BP / Meta 指导**  

```env
META_SOURCE=auto
STRATZ_API_TOKEN=   # https://stratz.com/api
STRATZ_BRACKET=high
```

人多用时请各自注册 Token，不要共享一个 Key。详见 [docs/BP_META.md](docs/BP_META.md)。

健康检查（助手已启动时）：

```powershell
python -m dodoclaw health
```

## 语音 ASR / TTS（可选 Step Plan 音频）

| Backend | 类型 | 说明 |
|---------|------|------|
| `mock` | ASR/TTS | 打字 / 只打印（默认） |
| `whisper` | ASR | 本地 faster-whisper |
| `edge` | TTS | 微软 Edge 在线语音 |
| **`stepfun_plan`** | ASR/TTS | 阶跃 Coding Plan：`stepaudio-2.5-asr` / `stepaudio-2.5-tts` |
| `stepfun` | ASR/TTS | 阶跃标准 `/v1` 音频接口 |

GUI 左侧「语音 ASR / TTS」可切换；或：

```env
STT_BACKEND=stepfun_plan
STT_MODEL=stepaudio-2.5-asr
TTS_BACKEND=stepfun_plan
TTS_MODEL=stepaudio-2.5-tts
TTS_VOICE=cixingnansheng
STEPFUN_API_KEY=...
```

参考官方：[Step Plan 语音模型接入](https://platform.stepfun.com/docs/zh/step-plan/integrations/audio-api)。

## LLM Provider（国内优先）

所有 Provider 均为 **OpenAI Chat Completions 兼容**。GUI 左侧可切换；也可写 `.env`。

| ID | 名称 | 默认 Base URL |
|----|------|----------------|
| `stepfun_plan` | 阶跃星辰 Step Plan（Coding Plan） | `https://api.stepfun.com/step_plan/v1` |
| `stepfun` | 阶跃星辰标准 API | `https://api.stepfun.com/v1` |
| `deepseek` | **DeepSeek** ★默认（`deepseek-flash`，关闭思考模式） | `https://api.deepseek.com` |
| `dashscope` | 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `zhipu` | 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` |
| `moonshot` | Kimi 月之暗面 | `https://api.moonshot.cn/v1` |
| `siliconflow` | 硅基流动 | `https://api.siliconflow.cn/v1` |
| `volcengine` | 豆包 / 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` |
| `minimax` / `yi` / `baichuan` | MiniMax / 零一 / 百川 | 见 `providers.py` |
| `xai` / `openai` / `custom` | Grok / OpenAI / 自定义 | 可改 Base URL |

```env
LLM_PROVIDER=stepfun_plan
LLM_API_KEY=你的密钥
# 可选覆盖：
# LLM_BASE_URL=https://api.stepfun.com/step_plan/v1
# LLM_MODEL=step-3.7-flash
# 或使用 STEPFUN_API_KEY / DEEPSEEK_API_KEY / DASHSCOPE_API_KEY …
```

> Step Plan / Coding Plan 必须用 **`stepfun_plan`** 端点（`/step_plan/v1`），不要用标准 `/v1`，否则走不到订阅额度。

未配置 Key 时仍可运行，回答为离线占位文案。

## 开发

```powershell
pip install -e ".[dev]"
pytest
```

## 路线图（建议）

- [ ] 全局热键 Push-to-Talk（非阻塞）
- [ ] 更精细的物品/技能 CD 与出装模板库
- [ ] 系统托盘 + 轻量 Overlay
- [ ] 分路/英雄专精提示
- [ ] 多语言与自定义提醒规则编辑器

## License

MIT
