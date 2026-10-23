# DoDoClaw 社区推广文案（可直接复制）

## 短介绍（QQ / 微信 / Discord）

> **DoDoClaw** — Dota 2 语音/文字教练助手（Windows 便携版）  
> 读局（GSI）+ AI 建议 + 神符/买活提醒。解压即用，不用装 Python。  
> 使用：解压 → 在 exe 同目录的 `.env` 填 Key → 开 `DoDoClaw.exe` → 安装 GSI → 重启 Dota → 开打提问。

## 使用步骤（给玩家）

1. 下载并解压 `DoDoClaw-win64.zip`
2. 双击 **DoDoClaw.exe**
3. 服务商默认 **DeepSeek**（模型 deepseek-flash）；想换阶跃星辰 Step Plan、通义、智谱、Kimi、硅基流动等，改 `config\settings.yaml` 里的 `coach.provider`  
4. 在 exe 同目录的 `.env` 里填对应的 **API Key**（`.env` 只放 Key），回到设置页点 **重新读取**  
5. 点击 **安装 Dota GSI 配置**（自动写入 Steam 目录）  
6. **完全退出并重启 Dota 2**（只重开一局有时不够）  
7. 点击 **启动服务**，进入对局后在输入框提问，例如：  
   - 「现在该出什么？」  
   - 「买活值不值？」  
   - 「对面可能在哪？」  

## 隐私与安全说明

- API Key **只保存在你电脑** exe 同目录的 `.env`，不上传到本项目服务器  
- GSI 只在本机 `127.0.0.1` 收 Dota 推送，不访问外网对局数据  
- 提问内容会发给你在 `settings.yaml` 里选的服务商用于生成回答（受该服务商条款约束）  
- 本工具 **不修改游戏内存、不注入、不读屏挂**，属于官方支持的 GSI 监听

## 常见问题

**Q: 一直「等待 Dota 推送」？**  
A: 确认已点「安装 GSI」、已完全重启 Dota、已进入对局（观战/DEMO 模式数据字段可能不同）。

**Q: 没 API Key 能用吗？**  
A: 可以启动界面和 GSI，但教练回答为离线占位；完整建议需要 Key。

**Q: 杀毒软件拦截？**  
A: 自打包 exe 无官方签名时可能被误报。可从源码自行 `build_app.ps1` 构建，或添加信任。

**Q: 能商用/二创吗？**  
A: MIT 协议，欢迎社区二次分发与改进，建议保留项目名与开源地址。

## 开发者构建

```powershell
git clone <your-repo>
cd DoDoClaw
powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1
```

产物：`dist/DoDoClaw-win64.zip`
