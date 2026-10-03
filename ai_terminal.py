from openai import OpenAI
import io, sys, re, ast, base64
import tempfile, subprocess, os, threading
import turtle
DANGER_FUNC = {"open", "eval", "exec", "compile"}
# 模块白名单：只允许导入绘图和学习需要的安全模块，其余一律拒绝
SAFE_MODULE = {
    "turtle", "math", "random", "time", "colorsys", "itertools",
    "datetime", "copy", "functools", "tkinter", "string", "statistics",
    "decimal", "fractions", "json", "re", "collections", "textwrap",
    "pprint", "heapq", "bisect", "base64", "uuid",
    "openai",  # 网络请求库：只能调用API，不能动文件和系统命令
}
class DangerChecker(ast.NodeVisitor):
    def __init__(self):
        self.has_danger = False
        self.msg = ""
    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            if node.func.id == "__import__":
                # __import__只允许导入白名单里的安全模块；参数不是明确字符串的一律拒绝
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
    use_turtle = "turtle" in code
    use_input = "input(" in code
    if use_turtle:
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
    else:
        full_code = code
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        tmp_path = f.name
    # 有input()的交互程序：直接接管终端，让用户输入数字
    if use_input:
        try:
            proc = subprocess.Popen([sys.executable, tmp_path])
            proc.wait()
            return "程序运行完毕。"
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass
    # 普通程序：捕获输出（强制子进程用UTF-8编码，解决Windows中文乱码）
    proc = subprocess.Popen(
        [sys.executable, tmp_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}
    )
    if use_turtle:
        # 绘图：后台线程等窗口关闭后读输出并删临时文件
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
        return "绘图进程已启动，关闭绘图窗口后子进程结束。"
    else:
        # 纯计算：等跑完直接拿输出
        out, err = proc.communicate()
        try:
            os.unlink(tmp_path)
        except:
            pass
        result = ""
        if out and out.strip():
            result += out.strip() + "\n"
        if err and err.strip():
            result += "报错：" + err.strip()
        return result.strip()

system_prompt = """你是严谨的助手，精通Python、C语言，懂编译原理、内存管理。全程使用中文思考和回答，思考过程（reasoning）也必须用中文，绝对不要用英文思考。记住对话上下文。
【语言强制规则，必须严格遵守】
1. 思考过程（内部推理、reasoning_content）必须全部用中文，禁止用英文思考。
2. 正式回答也必须用中文。
3. 只有代码、API名称、技术术语可以保留英文。
【代码输出规则，强制遵守，违反会导致程序出错】
1. 用户要求写代码/绘图：**只输出```python ... ```代码块，代码块外面绝对不能写任何文字，包括解释、问候、提问等任何内容**。
2. 用户没有要求写代码：正常文字回答，不要输出代码块。
3. 禁止生成文件读写、调用系统命令的代码。
4. 生成turtle绘图代码时，第二行必须写 turtle.getscreen().tracer(0)，绘图结尾只用 turtle.update()，绝对不要写 turtle.done()。
5. 输出内容结束后，绝对不要自己添加"AI：""你："这类对话前缀，输出完就停。
6. 写函数时，只输出函数定义本身，绝对不要附带任何测试调用、print语句、if __name__ == "__main__"块或示例调用代码。用户自己会测试，你只负责给出函数代码。"""
messages = [{"role":"system", "content": system_prompt}]
last_code = None  # 记住上一次AI生成的代码块，供"保存代码"指令使用
thinking_mode = True  # 深度思考开关，默认开启
current_model = "glm-4-flash"  # 当前使用的模型（智谱官方免费模型）
config_file = "ai_terminal_config.txt"  # 配置文件，保存用户设置

def load_config():
    """加载配置文件，读取上次使用的模型"""
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
    """保存配置到文件"""
    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(f"current_model={current_model}\n")
            f.write(f"glm_key={glm_key}\n")
            f.write(f"glm_base={glm_base}\n")
    except:
        pass
glm_key = ""  # 开源版：首次运行后用 "设置GLM key：你的key" 配置
glm_base = "https://open.bigmodel.cn/api/paas/v4"  # 智谱官方接口地址

def get_client_config(model_name):
    """根据模型名返回对应的api_key和base_url"""
    return glm_key, glm_base

if __name__ == "__main__":
    load_config()  # 加载上次的配置
    print("配置加载完成。")
    print(f"当前使用模型：{current_model}")
    print("指令：clear清空记忆 | 开启深度思考模式 | 关闭深度思考模式")
    print("      切换模型：模型名 | 设置GLM key：你的key | 设置GLM接口：你的中转地址")
    print("      保存代码：把上一次AI写的代码存成.py文件")
    print("      \"\"\"进入多行输入模式（粘贴多行文本用） | exit退出\n")
    while True:
        try:
            user_msg = input("你：")
        except (KeyboardInterrupt, EOFError):
            print("\n程序退出，再见！")
            break
        # 多行输入模式：三引号进入，再输入三引号结束
        MULTI_END = {'"""', "'''"}
        if user_msg.strip() in MULTI_END:
            print("（多行输入模式，再输入三引号结束）")
            lines = []
            while True:
                line = input("| ")
                if line.strip() in MULTI_END:
                    break
                lines.append(line)
            user_msg = "\n".join(lines)
        if user_msg == "clear":
            messages = [{"role":"system", "content": system_prompt}]
            print("AI：聊天记忆已经清空！")
            continue
        if user_msg == "开启深度思考模式":
            thinking_mode = True
            print("AI：深度思考模式已开启，回答会更慢但更严谨。")
            continue
        if user_msg == "关闭深度思考模式":
            thinking_mode = False
            print("AI：深度思考模式已关闭，恢复快速回答。")
            continue
        if user_msg.startswith("切换模型"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                new_model = parts[1].strip()
                api_key, base_url = get_client_config(new_model)
                if not api_key or not base_url:
                    print(f"AI：切换失败，模型 {new_model} 需要先配置API key和接口地址。")
                else:
                    current_model = new_model
                    save_config()
                    print(f"AI：已切换到模型：{current_model}，下次启动自动使用此模型。")
            else:
                print(f"AI：当前使用模型：{current_model}")
                glm_status = "已配置" if glm_key else "未配置key"
                print(f"  glm-4-flash（{glm_status}）")
                print("AI：切换请输入：切换模型：模型名")
            continue
        if user_msg.startswith("设置GLM key"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                glm_key = parts[1].strip()
                save_config()
                print("AI：GLM API key已设置成功，已保存。")
            else:
                print("AI：用法示例：设置GLM key：你的API key")
            continue
        if user_msg.startswith("设置GLM接口"):
            parts = re.split(r'[:：]', user_msg, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                glm_base = parts[1].strip()
                save_config()
                print(f"AI：GLM接口地址已设置为：{glm_base}，已保存。")
            else:
                print("AI：用法示例：设置GLM接口：https://你的中转地址/v1")
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
                print("AI：还没有可保存的代码，先让我写一段代码。")
            continue
        if user_msg == "exit":
            print("AI：程序退出，再见！")
            break
        messages.append({"role":"user", "content": user_msg})
        try:
            api_key, base_url = get_client_config(current_model)
            if not api_key:
                print(f"AI：错误，模型 {current_model} 的API key未设置。")
                print("AI：请先输入：设置GLM key：你的API key")
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
