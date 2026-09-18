# -*- coding: utf-8 -*-
"""
本地 AI 终端（开源版）
功能：命令行对话、流式输出、深度思考显示、turtle 自动绘图、AST 安全检查、代码保存

使用方法：
1. 安装依赖：pip install openai
2. 运行：python ai_terminal.py
3. 首次使用在终端里输入：
   设置GLM key：你的API key
   设置GLM接口：你的中转地址/v1
   切换模型：你的模型名
   （或者直接在下面代码里把 deepseek_key / glm_key 改成你自己的）
"""
from openai import OpenAI
import sys, re, ast, os
import tempfile, subprocess, threading
import turtle

DANGER_FUNC = {"open", "eval", "exec", "compile"}
SAFE_MODULE = {
    "turtle", "math", "random", "time", "colorsys", "itertools",
    "datetime", "copy", "functools", "tkinter", "string", "statistics",
    "decimal", "fractions", "json", "re", "collections", "textwrap",
    "pprint", "heapq", "bisect", "base64", "uuid",
    "openai",
}

class DangerChecker(ast.NodeVisitor):
    def __init__(self):
        self.has_danger = False
        self.msg = ""
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                mod_name = None
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    mod_name = node.args[0].value.split(".")[0]
                if mod_name not in SAFE_MODULE:
                    if node.args and isinstance(node.args[0], ast.Constant):
                        shown = node.args[0].value
                    else:
                        shown = "不明模块"
                    self.has_danger = True
                    self.msg = f"【AST拦截】__import__只允许导入绘图安全模块，禁止导入：{shown}"
            elif node.func.id in DANGER_FUNC:
                self.has_danger = True
                self.msg = f"【AST拦截】禁止调用危险函数：{node.func.id}"
        self.generic_visit(node)
    def visit_Import(self, node):
        for name in node.names:
            root = name.name.split(".")[0]
            if root not in SAFE_MODULE:
                self.has_danger = True
                self.msg = f"【AST拦截】只允许导入白名单安全模块，禁止导入：{name.name}"
        self.generic_visit(node)
    def visit_ImportFrom(self, node):
        root = (node.module or "").split(".")[0]
        if root not in SAFE_MODULE:
            self.has_danger = True
            self.msg = f"【AST拦截】只允许导入白名单安全模块，禁止导入：{node.module}"
        self.generic_visit(node)

def is_code_safe(code: str):
    if re.search(r"turtle\.done\(\)", code):
        return False, "【代码检查】禁止使用turtle.done()，请使用turtle.update()"
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"语法错误：{e}"
    checker = DangerChecker()
    checker.visit(tree)
    return not checker.has_danger, checker.msg

def run_python_code(code):
    safe_ok, msg = is_code_safe(code)
    if not safe_ok:
        return msg
    prefix = """
import turtle
screen = turtle.getscreen()
def on_close():
    screen.bye()
screen._root.protocol("WM_DELETE_WINDOW", on_close)
"""
    suffix = """
try:
    turtle.update()
    turtle.done()
except:
    pass
"""
    full_code = prefix + code + suffix
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        tmp_path = f.name
    try:
        proc = subprocess.Popen(
            [sys.executable, tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8"
        )
        return "绘图进程已启动，关闭绘图窗口后子进程结束。"
    finally:
        def delayed_delete(path, p):
            out, err = p.communicate()
            if out and out.strip():
                print(f"\n===== 绘图程序输出 =====\n{out.strip()}")
            if err and err.strip():
                print(f"\n===== 绘图程序报错 =====\n{err.strip()}")
            try:
                os.unlink(path)
            except:
                pass
        threading.Thread(target=delayed_delete, args=(tmp_path, proc), daemon=True).start()

system_prompt = """你是严谨的助手，精通Python。支持中文，记住对话上下文。
【代码输出规则】
1. 用户要求写代码/绘图：只输出```python ... ```代码块，代码块外面不要写任何文字。
2. 用户没有要求写代码：正常文字回答。
3. 禁止生成文件读写、调用系统命令的代码。
4. 生成turtle绘图代码时，第二行必须写 turtle.getscreen().tracer(0)，绘图结尾只用 turtle.update()，绝对不要写 turtle.done()。
5. 输出结束后不要自己加"AI："这种前缀。"""

messages = [{"role":"system", "content": system_prompt}]
last_code = None
thinking_mode = False
current_model = "deepseek-v4-flash-free"
config_file = "ai_terminal_config.txt"

def load_config():
    global current_model, glm_key, glm_base
    try:
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("current_model="):
                        current_model = line.split("=", 1)[1]
                    elif line.startswith("glm_key="):
                        glm_key = line.split("=", 1)[1]
                    elif line.startswith("glm_base="):
                        glm_base = line.split("=", 1)[1]
    except:
        pass

def save_config():
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(f"current_model={current_model}\n")
            f.write(f"glm_key={glm_key}\n")
            f.write(f"glm_base={glm_base}\n")
    except:
        pass

deepseek_key = ""
deepseek_base = "https://你的中转地址/v1"
glm_key = ""
glm_base = "https://你的中转地址/v1"

def get_client_config(model_name):
    if model_name.startswith("glm-"):
        return glm_key, glm_base
    else:
        return deepseek_key, deepseek_base

if __name__ == "__main__":
    load_config()
    print("配置加载完成。")
    print(f"当前使用模型：{current_model}")
    print("指令：clear清空记忆 | 开启/关闭深度思考模式 | 切换模型：模型名")
    print("      设置GLM key：你的key | 设置GLM接口：你的地址")
    print("      保存代码 | \"\"\"多行输入模式 | exit退出\n")
    while True:
        try:
            user_msg = input("你：")
        except (KeyboardInterrupt, EOFError):
            print("\n程序退出，再见！")
            break
        if user_msg.strip() == '"""':
            print("（多行输入模式，再输入 \"\"\" 结束）")
            lines = []
            while True:
                line = input("| ")
                if line.strip() == '"""':
                    break
                lines.append(line)
            user_msg = "\n".join(lines)
        if user_msg == "clear":
            messages = [{"role":"system", "content": system_prompt}]
            print("AI：聊天记忆已经清空！")
            continue
        if user_msg == "开启深度思考模式":
            thinking_mode = True
            print("AI：深度思考模式已开启。")
            continue
        if user_msg == "关闭深度思考模式":
            thinking_mode = False
            print("AI：深度思考模式已关闭。")
            continue
        if user_msg.startswith("切换模型"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                new_model = parts[1].strip()
                api_key, base_url = get_client_config(new_model)
                if not api_key or not base_url:
                    print(f"AI：切换失败，模型 {new_model} 需要先配置API key。")
                else:
                    current_model = new_model
                    save_config()
                    print(f"AI：已切换到模型：{current_model}")
            else:
                print(f"AI：当前使用模型：{current_model}")
            continue
        if user_msg.startswith("设置GLM key"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                glm_key = parts[1].strip()
                save_config()
                print("AI：GLM key已设置成功。")
            continue
        if user_msg.startswith("设置GLM接口"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                glm_base = parts[1].strip()
                save_config()
                print("AI：GLM接口地址已设置。")
            continue
        if user_msg == "保存代码":
            if last_code:
                save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_code")
                os.makedirs(save_dir, exist_ok=True)
                n = 1
                while os.path.exists(os.path.join(save_dir, f"code_{n}.py")):
                    n += 1
                save_path = os.path.join(save_dir, f"code_{n}.py")
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(last_code)
                print(f"AI：代码已保存到：{save_path}")
            else:
                print("AI：还没有可保存的代码。")
            continue
        if user_msg == "exit":
            print("AI：程序退出，再见！")
            break
        messages.append({"role":"user", "content": user_msg})
        try:
            api_key, base_url = get_client_config(current_model)
            if not api_key:
                print(f"AI：错误，模型 {current_model} 的API key未设置。")
                continue
            client = OpenAI(api_key=api_key, base_url=base_url)
            request_params = {
                "model": current_model,
                "messages": messages,
                "stream": True
            }
            resp = client.chat.completions.create(**request_params)
            print(f"【{current_model}】AI：", end="", flush=True)
            full_text = ""
            is_thinking = False
            for chunk in resp:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    if thinking_mode and not is_thinking:
                        print("\n【思考中...】", end="", flush=True)
                        is_thinking = True
                    if thinking_mode:
                        print(delta.reasoning_content, end="", flush=True)
                if delta.content:
                    if is_thinking:
                        if thinking_mode:
                            print("\n【回答】", end="", flush=True)
                        is_thinking = False
                    print(delta.content, end="", flush=True)
                    full_text += delta.content
            print(flush=True)
            messages.append({"role":"assistant", "content": full_text})
            if "```python" in full_text:
                match = re.search(r"```python\s*(.*?)```", full_text, re.S)
                if match:
                    code_block = match.group(1).strip()
                    last_code = code_block
                    print("\n===== 本地代码执行结果 =====")
                    result = run_python_code(code_block)
                    print(result)
        except Exception as e:
            print(f"\n出错：{repr(e)}")
