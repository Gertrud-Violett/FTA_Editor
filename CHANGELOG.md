# 更新日志（CHANGELOG）

FTA/ETA Editor **中文版** 的改动记录。本中文版基于原作者 [Gertrud-Violett/FTA_Editor](https://github.com/Gertrud-Violett/FTA_Editor)（原版 1.5.1，BSD-2-Clause）进行中文化与功能扩展，**未改动原版核心的 FTA / ETA 故障树与事件树算法及逻辑**。

## [1.5.1-cn] 中文版首版

### 新增

- **界面与文档全面简体中文化**：
  - `src/FTA_Editor_UI.py`：菜单、按钮、提示、AI 助手对话等界面文案中文化
  - `README.md`、`QUICKSTART.md`：中文版说明与快速入门文档
- **Windows 一键启动脚本**：新增 `启动FTA编辑器.bat`，中文用户直接双击即可运行
- **扩展 AI 服务商支持**（`src/ai_providers.py`）：
  - 在原有 OpenAI / Anthropic Claude / Google Gemini / Microsoft Copilot 基础上，新增 5 家国内 / 本地服务商（均走 OpenAI 兼容接口，复用现有 `openai` SDK，无需新增依赖）：
    - **DeepSeek**：`deepseek-chat` / `deepseek-reasoner`
    - **通义千问**（阿里云 DashScope）：`qwen-max` / `qwen-plus` / `qwen-turbo`
    - **智谱清言**（GLM）：`glm-4-plus` / `glm-4-air` / `glm-4-flash`
    - **Kimi**（月之暗面）：`moonshot-v1-8k` / `moonshot-v1-32k` / `moonshot-v1-128k`
    - **Ollama 本地**（免密钥）：`qwen2.5` / `llama3.1`
  - 在 AI 设置界面即可选择上述服务商，支持「测试连接」与「拉取模型列表」

### 说明

- 本中文版为镜像/汉化仓库，遵循 [BSD-2-Clause](LICENSE) 开源协议，版权归原作者 makkiblog.com 所有
- 原仓库：https://github.com/Gertrud-Violett/FTA_Editor
- 本仓库：https://github.com/iSun0613/FTA_Editor_Chinese