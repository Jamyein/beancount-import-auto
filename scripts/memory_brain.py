# memory_brain.py
import sys
import json
from pathlib import Path
from openai import OpenAI

sys.dont_write_bytecode = True

# ---------- paths ----------

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.json"
CACHE_FILE = BASE_DIR / "config" / "mapping.json"

# ---------- load config ----------

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

openai_cfg = config["openai"]
ALLOWED_ACCOUNTS = set(config.get("my_accounts", []))

# ---------- OpenAI client (DeepSeek compatible) ----------

client = OpenAI(
    api_key=openai_cfg["api_key"],
    base_url=openai_cfg["api_base"]
)

MODEL = openai_cfg["model"]

# ---------- Memory Brain ----------

class MemoryBrain:
    def __init__(self):
        self.mapping = self._load_mapping()

    def _load_mapping(self) -> dict:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_mapping(self):
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.mapping, f, ensure_ascii=False, indent=2)

    def _ai_classify(self, payee: str, note: str, raw_category: str, current_allowed: set) -> str:
        # 获取所有合法账户（my_accounts + 本次匹配到的 asset_mapping 账户）
        # 注意：这里需要确保你已经按照上一条回复修改了 classify 以便传入 dynamic_accounts
        
        accounts_text = "\n".join(sorted(list(current_allowed)))

        prompt = f"""
你是一个专业的 Beancount 记账分类助手。

【已知信息】
1. 账单原始分类（最重要參考）：{raw_category}
2. 商户名称：{payee}
3. 商品信息：{note}

【待选账户列表】
{accounts_text}

【任务】
请从上述“待选账户列表”中选择一个最合适的账户。

【规则 - 必须遵守】
1. 必须优先参考“账单原始分类”进行逻辑推断。
2. 必须【只能】从提供的“待选账户列表”中选择。
3. 如果无法确定，请选择列表中的支出类账户（Expenses: 开头）。
4. 只能返回账户名本身，不要包含任何解释、标点或多余文字。
"""

        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            return resp.choices[0].message.content.strip().replace('"', '').replace('。', '')
        except Exception as e:
            print(f"❌ AI 接口异常: {e}")
            return "Expenses:Unknown"

    def _confirm_account_dynamic(self, suggested: str, current_allowed: set) -> str:
        """
        人工确认函数（修复了 AttributeError）
        """
        while True:
            print(f"\n🤖 AI 建议账户：{suggested}")
            user_input = input("请输入账户（回车确认 / 手动修改）：\n> ").strip()

            final = user_input if user_input else suggested

            if final in current_allowed:
                return final

            print(f"❌ 非法账户：'{final}'，该账户不在 my_accounts 或本次资产映射中。")
            print("合法选项示例（前10个）：")
            for acc in sorted(list(current_allowed))[:10]:
                print(f"  - {acc}")

    def classify(self, payee: str, raw_category: str, note: str, raw_account: str) -> str:
        """
        分类主逻辑
        """
        # 1. 检查缓存 (Key 包含原始分类，确保分类不同时能区分)
        key = f"{payee.strip()}|{raw_category.strip()}"
        if key in self.mapping:
            return self.mapping[key]

        print(f"\n🆕 发现新商户：{payee}")
        print(f"   账单原始分类：{raw_category}")

        # 2. 构建本次交易合法的账户集合
        current_allowed = set(config.get("my_accounts", []))
        
        # 资产映射检测（转账处理）
        matched_asset_account = None
        for kw, acc in config.get("asset_mapping", {}).items():
            if kw.lower() in payee.lower():
                matched_asset_account = acc
                break
        
        if matched_asset_account:
            current_allowed.add(matched_asset_account)
            print(f"ℹ️ 检测到资产关键词，允许选择：{matched_asset_account}")

        # 3. 调用 AI 分类 (传入所有上下文)
        suggested = self._ai_classify(payee, note, raw_category, current_allowed)

        # 4. 人工确认 (调用上面定义的函数)
        final_account = self._confirm_account_dynamic(suggested, current_allowed)

        # 5. 保存映射
        self.mapping[key] = final_account
        self._save_mapping()

        return final_account
