#!/usr/bin/env python3
"""刘永昌老师 AI 聊天终端
无外部依赖，启动后直接与角色对话。
"""
import json, os, sys, urllib.request, urllib.error, atexit, shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "角色蒸馏包")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "lyc_config.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, "lyc_history.json")

PROVIDERS = [
    {
        "name": "DeepSeek（推荐，注册送额度）",
        "url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "link": "https://platform.deepseek.com",
        "note": "注册后创建 API Key，充值几块钱够用很久",
    },
    {
        "name": "SiliconFlow（注册送额度）",
        "url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "link": "https://cloud.siliconflow.cn",
        "note": "注册送 14 元体验金，模型选择很多",
    },
    {
        "name": "OpenAI",
        "url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "link": "https://platform.openai.com",
        "note": "需海外信用卡，gpt-4o-mini 最便宜",
    },
    {
        "name": "阿里百炼",
        "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-plus",
        "link": "https://bailian.console.aliyun.com",
        "note": "阿里云账号可直接用，qwen-plus 性价比高",
    },
    {
        "name": "智谱 GLM",
        "url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-flash",
        "link": "https://bigmodel.cn",
        "note": "注册送额度，glm-4-flash 免费",
    },
    {
        "name": "自定义",
        "url": "",
        "model": "",
        "link": "",
        "note": "手动输入 Base URL 和模型名",
    },
]

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "",
    "model": "",
    "temperature": 0.8,
    "max_tokens": 2048,
    "greeting": True,
}

# ── 配置 ──
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return None

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── 加载角色提示词 ──
def load_system_prompt():
    prompt_file = os.path.join(DATA_DIR, "刘永昌_完整角色指令_V2.0.txt")
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read()
    # fallback: 拼接角度文件
    parts = []
    for fn in ["角度一_课堂教学者_刘永昌.md", "角度二_班主任管理者_刘永昌.md"]:
        fp = os.path.join(DATA_DIR, fn)
        if os.path.exists(fp):
            with open(fp, "r", encoding="utf-8") as f:
                parts.append(f.read())
    return "\n\n---\n\n".join(parts) if parts else "[错误: 未找到角色数据文件]"

# ── 对话历史 ──
def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(h):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h[-50:], f, ensure_ascii=False, indent=2)

# ── API 调用 ──
def chat_completion(messages, cfg):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    body = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg["temperature"],
        "max_tokens": cfg["max_tokens"],
    }
    url = cfg["base_url"].rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"

    # 先试流式
    body["stream"] = True
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:300]
        print(f"\n[API 错误 {e.code}] {err_body}")
        if e.code == 404 and "not found" in err_body.lower():
            print(f"[提示] 模型 '{cfg['model']}' 不存在，用 /setup 重新配置")
        return None
    except urllib.error.URLError as e:
        print(f"\n[网络错误] 无法连接到 {cfg['base_url']}")
        print(f"[原因] {e.reason}")
        return None

    full = ""
    buf = ""
    for chunk in resp:
        buf += chunk.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                    delta = obj.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full += content
                        print(content, end="", flush=True)
                except json.JSONDecodeError:
                    pass

    # 流式没出内容 → fallback 非流式
    if not full:
        body.pop("stream")
        req2 = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
        try:
            resp2 = urllib.request.urlopen(req2, timeout=120)
        except urllib.error.HTTPError as e:
            err2 = e.read().decode("utf-8", errors="replace")[:300]
            print(f"\n[API 错误 {e.code}] {err2}")
            return None
        result = json.loads(resp2.read().decode("utf-8"))
        full = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if full:
            print(full, end="", flush=True)
        else:
            print("[错误] API 返回了空回复", flush=True)
            return None

    return full

# ── 测试连接 ──
def test_connection(cfg):
    print("\n[正在测试连接...]", end=" ", flush=True)
    test_msgs = [
        {"role": "system", "content": "你是一个测试助手，只回复OK，不要其他内容。"},
        {"role": "user", "content": "测试"},
    ]
    result = chat_completion(test_msgs, cfg)
    if result:
        print("\n[连接成功]")
        return True
    return False

# ── 首次设置向导 ──
def first_setup():
    print()
    print("=" * 56)
    print("  刘永昌老师 AI 聊天终端 · 首次设置")
    print("=" * 56)
    print()
    print("选择一个 AI 服务提供商（需要 API Key）：")
    print()

    for i, p in enumerate(PROVIDERS, 1):
        print(f"  [{i}] {p['name']}")
        print(f"      {p['note']}")
        print()

    while True:
        try:
            choice = input(f"请选择 (1-{len(PROVIDERS)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDERS):
                break
        except ValueError:
            pass
        print(f"输入 1-{len(PROVIDERS)} 之间的数字")

    provider = PROVIDERS[idx]
    print()

    if provider["name"] != "自定义":
        print(f"  → 去 {provider['link']} 注册并创建 API Key")
        print()

    api_key = input("API Key: ").strip()
    while not api_key:
        api_key = input("API Key（不能为空）: ").strip()

    base_url = provider["url"]
    model = provider["model"]

    if provider["name"] == "自定义":
        base_url = input("Base URL: ").strip()
        model = input("Model: ").strip()
    else:
        print(f"  Base URL: {base_url}")
        print(f"  Model:    {model}")
        use_default = input("\n使用以上默认值？(Y/n): ").strip().lower()
        if use_default == "n":
            base_url = input("Base URL: ").strip() or base_url
            model = input("Model: ").strip() or model

    cfg = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": DEFAULT_CONFIG["temperature"],
        "max_tokens": DEFAULT_CONFIG["max_tokens"],
        "greeting": True,
    }

    test_now = input("\n测试连接？(Y/n): ").strip().lower()
    if test_now != "n":
        if test_connection(cfg):
            print("[配置可用]")
        else:
            print("[连接失败，仍将保存配置，可稍后修改]")

    save_config(cfg)
    print(f"\n[配置已保存: {CONFIG_FILE}]")
    return cfg

# ── 交互循环 ──
def main():
    cfg = load_config()
    if not cfg:
        cfg = first_setup()
    elif not cfg.get("api_key"):
        print("\n[配置文件中的 API Key 为空，进入设置]")
        cfg = first_setup()

    system_prompt = load_system_prompt()
    history = load_history()
    atexit.register(lambda: save_history(history))

    print()
    print("=" * 56)
    print(f"  刘永昌老师 × {cfg['model']}")
    print("=" * 56)
    print(f"  角色数据: 角色蒸馏包/ ({len(system_prompt)} 字符)")
    print(f"  输入 /help 查看命令")
    print()

    messages = [{"role": "system", "content": system_prompt}]
    for m in history[-10:]:
        if m["role"] in ("user", "assistant"):
            messages.append(m)

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        cmd = user_input.lower()

        if cmd == "/quit" or cmd == "/exit":
            break

        elif cmd == "/new":
            messages = [{"role": "system", "content": system_prompt}]
            print("[对话历史已清空]")
            continue

        elif cmd == "/help":
            print("""命令:
  /help     显示帮助
  /new      清空当前对话
  /history  查看保存的消息数
  /prompt   查看角色设定（前2000字）
  /config   查看当前配置
  /setup    重新设置 API
  /quit     退出""")
            continue

        elif cmd == "/history":
            print(f"[当前对话: {len(messages)-1} 条 | 历史文件: {len(history)} 条]")
            continue

        elif cmd == "/prompt":
            print(system_prompt[:2000])
            if len(system_prompt) > 2000:
                print(f"... ({len(system_prompt)} 字符，仅显示前 2000)")
            continue

        elif cmd == "/config":
            safe = {k: v for k, v in cfg.items() if k != "api_key"}
            print(json.dumps(safe, ensure_ascii=False, indent=2))
            continue

        elif cmd == "/setup":
            cfg = first_setup()
            print("[重新设置完成]")
            continue

        messages.append({"role": "user", "content": user_input})
        print("刘永昌: ", end="", flush=True)
        reply = chat_completion(messages, cfg)
        print()

        if reply:
            messages.append({"role": "assistant", "content": reply})
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})

if __name__ == "__main__":
    main()
