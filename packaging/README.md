# 打包与社区分发

## 产物

| 文件 | 说明 |
|------|------|
| `dist/DoDoClaw/DoDoClaw.exe` | 双击启动桌面 App |
| `dist/DoDoClaw-win64.zip` | 发给社区的便携包 |

用户**无需安装 Python**。解压即用，配置写在 exe 同目录的 `.env`。

## 一键构建（开发者）

```powershell
cd D:\Project\DoDoClaw
powershell -ExecutionPolicy Bypass -File .\scripts\build_app.ps1
```

## 社区使用说明（可贴进群）

1. 解压 `DoDoClaw-win64.zip`
2. 双击 `DoDoClaw.exe`
3. 填入 [xAI API Key](https://console.x.ai) 并点「保存 Key」
4. 点「安装 Dota GSI 配置」→ **完全重启 Dota 2**
5. 点「启动服务」→ 进对局提问

## 开发时直接跑 GUI

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e ".[app]"
python -m dodoclaw gui
```

## 可选：加图标

把 `icon.ico` 放到 `packaging/icon.ico` 后重新打包即可。
