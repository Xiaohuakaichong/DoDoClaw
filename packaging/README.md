# 打包与社区分发

## 产物

| 文件 | 说明 |
|------|------|
| `dist/DoDoClaw/DoDoClaw.exe` | **请运行这个**（完整目录，含 `_internal`） |
| `dist/DoDoClaw-win64.zip` | 发给社区的便携包 |

用户**无需安装 Python**。解压即用，配置写在 exe 同目录的 `.env`。

### 常见错误：Failed to load Python DLL

若双击报：

```text
Failed to load Python DLL
...\build\dodoclaw\_internal\python314.dll
```

说明打开了 **`build\dodoclaw\DoDoClaw.exe`**。那是 PyInstaller **中间产物**，不能单独运行。

正确路径：

```text
D:\Project\DoDoClaw\dist\DoDoClaw\DoDoClaw.exe
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_app.ps1
```

分发时只发整个 `dist\DoDoClaw\` 文件夹（或 zip），不要只拷一个 exe，也不要发 `build\`。

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
