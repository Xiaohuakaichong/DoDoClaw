# 服务商管理（WebView2 预览版）

在 **设置 → 服务商管理** 统一配置 AI 教练的连接，以及云端语音复用的服务商 Key。

1. 在左侧选择预设，或点击「添加自定义」。
2. 填写接口地址、模型 ID 和 API Key。预设地址和模型也可修改，并可分别恢复默认。
3. 点击「仅保存」保留配置，或「保存并测试」发送一次简短请求验证连接，可能产生少量 API 费用。
4. 需要用于教练时，点击「用于 AI 教练」。仅选择列表或保存其他服务商，不会改变当前教练。

硅基流动与其他服务商共用同一套编辑表单，API Key 输入框始终可见。
保存后输入框清空；留空再次保存会保留原 Key。删除 Key 后，接口和模型配置仍然保留。
连接测试失败也会保留已保存的配置，可修改后重试。

自定义接口支持 OneAPI / NewAPI、兼容 OpenAI 的网关和本地模型服务，可保存多套配置，
各有独立 Key。填写 API 根地址，例如 `https://example.com/v1`；
误填末尾 `/chat/completions` 会自动移除。本机和局域网可用 HTTP，公网使用 HTTPS。
Key 必须单独填写，接口地址不接受用户名、密码或查询参数。

## 国内预设

| 服务商 | 默认接口地址 | 默认模型 |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `deepseek-ai/DeepSeek-V4-Flash` |
| 阶跃 Step Plan | `https://api.stepfun.com/step_plan/v1` | `step-3.7-flash` |
| 阶跃按量 | `https://api.stepfun.com/v1` | `step-2-mini` |
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3-flash` |
| Kimi | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` |
| 豆包 / 火山方舟 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-1-pro-260915` |
| MiniMax | `https://api.minimax.cn/v1` | `MiniMax-M3` |

另有零一万物、百川及 OpenAI、xAI 预设。模型可直接输入，实际可用型号及额度以自己的服务商账号为准。
本次更新核对了新增展示的通义、智谱、Kimi、豆包和 MiniMax 官方文档（2026-10-24），
没有使用真实 Key 调用这些收费接口。Kimi K3 使用其要求的固定温度；强制思考模型保留额外生成预算，
避免在思考结束前耗尽输出上限。

官方资料：

- [阿里百炼 OpenAI 兼容接口](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)
- [智谱 OpenAI 兼容接口](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)、[GLM 5.3 Flash](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash)
- [Kimi 模型列表](https://platform.kimi.com/docs/models)、[K3 请求参数](https://platform.kimi.com/docs/api/models-overview)
- [火山方舟接口与鉴权](https://docs.volcengine.com/docs/ark/base-url-and-authentication?lang=en)
- [MiniMax OpenAI 兼容接口](https://platform.minimax.cn/docs/api-reference/text-openai-api)

## 教练与语音

「教练与语音」页保留教练、识别和播报选择，以及声音、开关、试听和本地 Whisper 下载。
点击「配置服务商」或语音的「去填 Key」，直接打开对应服务商的配置，不会切换当前教练。

云端语音目前支持硅基流动与阶跃，复用各自已保存的 Key。Step Plan 与阶跃按量共用一个阶跃 Key，
删除时会提示这项关联。服务商管理里的地址和对话模型用于 AI 教练；云端识别、播报继续使用各自的官方音频接口。
本地 Whisper 和 Edge TTS 不需要 API Key。

## 本地保存与升级

Key 经现有 KeyStore 写入本机 `.env` 文件，仍是本机明文存储；页面和返回状态不会回显已保存的 Key。
非敏感连接写入 `config/settings.yaml` 的 `provider_configs`（预设）或 `coach.custom_providers`（自定义）。
当前教练的旧地址、模型和 Key 会沿用；后续切换服务商时，各家连接分别保留。
更新程序时保留原目录中的 `.env`、`config`、`data` 与 `logs`，重新启动应用后进入「服务商管理」即可使用。
