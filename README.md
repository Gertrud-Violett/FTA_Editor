# FTA/ETA Editor 中文版

FTA/ETA 事故树编辑器（中文版）：一款功能完整的故障树分析（FTA）与事件树分析（ETA）桌面软件，支持概率计算、可视化树编辑、AI 分析助手与多种格式导出。
本仓库为 [Gertrud-Violett/FTA_Editor](https://github.com/Gertrud-Violett/FTA_Editor) 的简体中文汉化版本，在原版基础上将界面与交互文本全面中文化，并附 Windows 一键启动脚本，方便中文用户直接下载使用。

## 相对原版的改进

本版本在原作者 [Gertrud-Violett/FTA_Editor](https://github.com/Gertrud-Violett/FTA_Editor) 的基础上，主要做了以下几点增强：

1. **全面简体中文化**：界面、菜单、按钮、提示与 AI 助手对话文案全部中文化，并新增 `启动FTA编辑器.bat` Windows 一键启动脚本，方便中文用户直接下载使用。
2. **扩展 AI 服务商支持**：在原有 OpenAI / Anthropic Claude / Google Gemini / Microsoft Copilot 之外，新增 5 家国内 / 本地服务商（均走 OpenAI 兼容接口、复用现有 `openai` SDK，无需新增任何依赖）：
   - **DeepSeek**：`deepseek-chat` / `deepseek-reasoner`
   - **通义千问**（阿里云 DashScope）：`qwen-max` / `qwen-plus` / `qwen-turbo`
   - **智谱清言**（GLM）：`glm-4-plus` / `glm-4-air` / `glm-4-flash`
   - **Kimi**（月之暗面）：`moonshot-v1-8k` / `moonshot-v1-32k` / `moonshot-v1-128k`
   - **Ollama 本地**（免密钥）：`qwen2.5` / `llama3.1`

> 以上均为「界面汉化 + 功能扩展」，未改动原版核心的 FTA / ETA 故障树与事件树算法及逻辑，遵循 BSD-2-Clause 协议。

## 功能特性

[![License: BSD-2-Clause](https://img.shields.io/badge/License-BSD2-yellow.svg)](https://opensource.org/license/bsd-2-clause)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-1.5.1-green.svg)](CHANGELOG.md)

- **交互式树编辑器**：实时图形预览，所见即所得
- **双分析模式**：FTA（自下而上的故障树分析）与 ETA（自上而下的事件树分析）
- **AI 智能助手**：内置对话式界面，支持故障树分析与改进建议
- **精确概率计算**：支持与门（AND）/ 或门（OR）逻辑门
- **可视化图形生成**：基于 Graphviz，逻辑门直接显示在节点中
- **多种导出格式**：JSON、XML、Excel（带层级结构）
- **零概率节点高亮**：快速定位问题节点
- **安全凭据存储**：API 密钥仅保存在本地，绝不入库

## 快速开始

### 方式一：Windows 一键启动（推荐）

1. 安装 [Python 3.10+](https://www.python.org/downloads/) 与 [Graphviz](https://graphviz.org/download/)（安装时勾选"Add to PATH"）
2. 双击运行 `启动FTA编辑器.bat`
3. 首次使用前请先安装依赖：`pip install -r requirements.txt`

### 方式二：命令行启动

```bash
# 克隆本仓库
git clone https://github.com/<你的用户名>/FTA_Editor_Chinese.git
cd FTA_Editor_Chinese

# 安装依赖
pip install -r requirements.txt

# 运行程序
python src/FTA_Editor_UI.py
```

### 环境要求

- Python 3.10+
- Graphviz（从 [graphviz.org](https://graphviz.org/download/) 下载安装）
- Python 依赖见 `requirements.txt`

## AI 助手配置（可选）

内置 AI 助手支持多家服务商：**OpenAI**、**Microsoft Copilot**、**Anthropic Claude**、**Google Gemini**，以及国内服务商 **DeepSeek**、**通义千问**、**智谱清言**、**Kimi**、**Ollama 本地**。

**快速配置：**
1. 获取 API 密钥：
   - **Google Gemini**：https://aistudio.google.com/apikey（提供免费额度）
   - **OpenAI**：https://platform.openai.com/api-keys
   - **Microsoft Copilot**：https://portal.azure.com（Azure OpenAI 服务）
   - **Anthropic Claude**：https://console.anthropic.com/api-keys
2. 打开 FTA Editor → 点击 AI 设置（⚙）
3. 选择服务商、粘贴 API 密钥、配置端点，点击"测试并保存"

凭据保存在本地 `~/.fta_editor/ai_credentials.json`（不会上传到仓库或云端）。

详细配置说明见 [docs/QUICK_AI_SETUP.md](docs/QUICK_AI_SETUP.md) 与 [docs/MULTI_PROVIDER_SETUP.md](docs/MULTI_PROVIDER_SETUP.md)。

### 快捷操作
- **分析故障树**：将评估与建议发送到对话窗口，不会修改你的树
- **更新故障树**：AI 生成完整 JSON 更新，经结构与安全性校验后替换当前故障树；已有节点保留，仅应用新增内容。AI 输出无效时会显示详细错误日志
- 可提问示例："这个失效模式可能缺少哪些根本原因？"、"请检查这棵树的概率"、"为选中节点建议更多失效模式"

## 使用说明

### 图形界面

```bash
python src/FTA_Editor_UI.py
```

**键盘快捷键：**
- `Ctrl+N`：新建分析
- `Ctrl+A`：添加节点
- `Ctrl+E`：编辑节点
- `Ctrl+D`：删除节点
- `Ctrl+S`：保存
- `Ctrl+R`：渲染图形

### 编程接口

```python
from src.FTA_Editor_core import FTACore

core = FTACore()
core.set_metadata(title="分析", mode="FTA")
core.load_from_json("data/examples/sampleFTA.json")
core.recalculate_probabilities()
core.export_to_excel("output.xlsx")
```

## 项目结构

```
FTA_Editor_Chinese/
├── src/                          # 源代码
│   ├── FTA_Editor_UI.py         # 图形界面（含 AI 对话，已汉化）
│   ├── FTA_Editor_core.py       # 核心业务逻辑
│   ├── AI_agent_handler.py      # AI 智能体与 API 处理
│   └── json_viewer.py           # 图形渲染器
├── tests/                        # 测试套件
├── data/examples/               # 示例数据
├── docs/                        # 文档
├── 启动FTA编辑器.bat             # Windows 一键启动脚本
└── requirements.txt             # Python 依赖
```

## 测试

```bash
python -m pytest tests/
```

## 分析模式

**FTA（故障树分析）**：自下而上的可靠性分析
- 顶事件 = 系统失效事件
- 底事件 = 部件失效原因
- 由部件失效概率计算系统失效概率

**ETA（事件树分析）**：自上而下的后果分析
- 顶事件 = 初始事件
- 底事件 = 最终后果
- 由事件序列计算后果概率

## 导出格式

- **JSON**：完整树数据（含元数据）
- **XML**：标准故障树格式
- **Excel**：带颜色编码的层级表格

## 文档

- [快速入门指南](QUICKSTART.md) - 三步上手
- [用户手册](docs/USER_GUIDE.md) - 完整使用说明
- **AI 服务商配置：**
  - [Microsoft Copilot 配置](docs/MICROSOFT_COPILOT_SETUP.md)
  - [多服务商配置](docs/MULTI_PROVIDER_SETUP.md)
- [ETA 模式](docs/ETA_MODE.md) - 事件树分析
- [API 参考](docs/API_REFERENCE.md) - 编程接口

## 常见问题

### AI 助手问题

**提示"AI 未配置"：**
- 点击 ⚙ 按钮，输入你的 API 凭据

**测试时"连接失败"：**
- 确认 API 密钥正确且有效
- 检查网络连接
- 确认 API 端点 URL 正确
- 使用 Azure 时确认部署名称正确

**响应缓慢：**
- 可改用 `gpt-4o-mini` 等更快模型
- 检查 API 调用限额

### 一般问题

**找不到 Graphviz：**
- 从 [graphviz.org](https://graphviz.org/download/) 安装
- 将 Graphviz 加入系统 PATH
- 重启程序

**图形不显示：**
- 确认已安装 Pillow：`pip install Pillow`
- 确认 Graphviz 安装正确

## 开源协议与致谢

本项目基于 **BSD-2-Clause** 协议开源，版权归原作者 makkiblog.com 所有。

- 原仓库：[Gertrud-Violett/FTA_Editor](https://github.com/Gertrud-Violett/FTA_Editor)
- 本中文版在原版基础上仅进行界面与文档的简体中文化，未改动核心算法与功能逻辑
- 使用、修改、再分发请遵守 [LICENSE](LICENSE) 中的条款

## 支持

- 问题反馈：[GitHub Issues](https://github.com/Gertrud-Violett/FTA_editor/issues)
- 示例数据：[data/examples/](data/examples/)
