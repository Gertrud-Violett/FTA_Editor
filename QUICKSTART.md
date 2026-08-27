# 快速入门指南

三步上手 FTA/ETA Editor 中文版。

**版本**：1.5.1（更新日期：2025年12月16日）

## 1. 安装

**环境要求：** Python 3.10+ 和 [Graphviz](https://graphviz.org/download/)

```bash
# 克隆并安装
git clone https://github.com/<你的用户名>/FTA_Editor_Chinese.git
cd FTA_Editor_Chinese
python install.py
```

或手动安装：

```bash
pip install -r requirements.txt
python src/FTA_Editor_UI.py
```

Windows 用户也可以直接双击 `启动FTA编辑器.bat` 一键启动。

## 2. 运行

```bash
python src/FTA_Editor_UI.py
```

## 3. 使用

1. **创建节点**：选中根节点，点击"添加节点"
2. **设置概率**：编辑节点，输入概率（0-1）
3. **设置逻辑门**：为非叶节点选择与门（AND）或或门（OR）
4. **选择模式**：FTA（故障分析）或 ETA（事件序列）
5. **查看图形**：逻辑门直接显示在节点框中
6. **导出**：保存为 JSON / Excel / XML 或渲染图形

### AI 快捷操作（可选）
- **分析故障树**：读取当前树并仅将分析/建议发送到对话窗口（不修改树）。
- **更新故障树**：由 AI 生成完整且经过校验的 JSON，一步替换整个故障树。已有节点保留，仅应用新增内容。

## AI 助手配置（可选）

AI 助手可以分析你的故障树并提出改进建议。

1. 从 [OpenAI Platform](https://platform.openai.com/) 获取 API 密钥
2. 在 AI 助手面板点击 ⚙（设置）
3. 输入 API 密钥，点击"测试并保存"
4. 开始对话！可提问或使用快捷操作

API 密钥保存在本地 `~/.fta_editor/ai_credentials.json`，绝不会进入仓库。

详细配置见 [README.md](README.md#ai-助手配置可选)。

## v1.5.1 更新内容

- ✅ **更新故障树按钮**：AI 返回完整 JSON，经校验后应用，可一步完成深层（多级）添加
- ✅ **健壮的 JSON 校验**：无效输出会被拒绝，并给出精确错误日志与问题定位
- ✅ **更深层的树**：界面支持任意嵌套深度，带自适应配色
- ✅ **多服务商 AI**：支持 OpenAI、Claude、Gemini，动态模型列表

## 键盘快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+N` | 新建分析 |
| `Ctrl+A` | 添加节点 |
| `Ctrl+E` | 编辑节点 |
| `Ctrl+D` | 删除节点 |
| `Ctrl+S` | 保存 |
| `Ctrl+R` | 渲染图形 |

## 需要帮助？

- 加载示例：`data/examples/sampleFTA.json`
- 文档：`docs/USER_GUIDE.md`
- AI 配置：见 [README.md](README.md#ai-助手配置可选)
- 测试安装：`python -m pytest tests/`
