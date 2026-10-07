#这是旧AI终端代码
# AI Terminal

本地 AI 命令行终端，支持流式对话、turtle 自动绘图、AST 安全沙箱、代码保存。

## 功能

- 流式输出对话，支持深度思考过程展示
- AI 生成 Python 代码后本地自动运行
- turtle 绘图自动开窗口、关窗口后清理临时文件
- AST 安全沙箱：禁止 `open/eval/exec/compile`，只允许导入白名单安全模块
- 交互程序 `input()` 直接接管终端
- 配置自动保存（模型、API key、接口地址）
- 三引号多行输入模式

## 安装

```bash
pip install openai
```

需要 Python 3.8+。

## 使用

```bash
python ai_terminal.py
```

首次运行后输入你的智谱 GLM API key：

```
设置GLM key：你的API key
```

默认模型 `glm-4-flash`（智谱免费模型），接口地址默认 `https://open.bigmodel.cn/api/paas/v4`。

## 内置命令

| 命令 | 作用 |
|---|---|
| `clear` | 清空聊天记忆 |
| `开启深度思考模式` / `关闭深度思考模式` | 开关思考过程显示 |
| `切换模型：模型名` | 切换模型 |
| `设置GLM key：你的key` | 配置 API key |
| `设置GLM接口：地址` | 配置中转接口 |
| `保存代码` | 把上一次 AI 写的代码存成 .py |
| `exit` | 退出 |

## 安全说明

- AI 生成的代码在 AST 层拦截危险调用和白名单外的导入
- 临时文件运行完自动删除
- API key 只保存在本地 `ai_terminal_config.txt`，不写入代码仓库

## License

MIT
