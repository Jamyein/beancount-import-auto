# scripts/init_beancount.py
import sys
import json
from pathlib import Path
from datetime import date

sys.dont_write_bytecode = True

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.json"

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

BEAN_FILE = BASE_DIR / "equity.beancount"

ASSET_MAPPING = config.get("asset_mapping", {})
CLASS_ACCOUNTS = config.get("my_accounts", [])

EQUITY_ACCOUNT = "Equity:Opening-Balances"
CURRENCY = "CNY"
OPEN_DATE = date.today().isoformat()


# ---------- helpers ----------

def ensure_file():
    if not BEAN_FILE.exists():
        BEAN_FILE.write_text("", encoding="utf-8")


def read_content():
    return BEAN_FILE.read_text(encoding="utf-8")


def account_exists(account: str, content: str) -> bool:
    return f"open {account}" in content


def write_open(account: str, content: str, f):
    if not account_exists(account, content):
        f.write(f"{OPEN_DATE} open {account}\n")


def opening_balance_exists(account: str, content: str) -> bool:
    return f"* \"Opening Balance\"\n  {account}" in content


def prompt_balance(account: str, label: str) -> float:
    while True:
        value = input(f"{account}（{label}）：\n> ").strip()
        if value == "":
            return 0.0
        try:
            return float(value)
        except ValueError:
            print("❌ 请输入合法数字")


# ---------- main ----------

def init_beancount():
    ensure_file()
    content = read_content()

    print("\n请输入账户初始余额（CNY），直接回车表示 0\n")

    with open(BEAN_FILE, "a", encoding="utf-8") as f:
        f.write("\n; ====== Auto Init Accounts ======\n\n")

        # ---------- open equity ----------
        write_open(EQUITY_ACCOUNT, content, f)

        # ---------- open assets / liabilities ----------
        for acc in sorted(set(ASSET_MAPPING.values())):
            write_open(acc, content, f)

        # ---------- open classification accounts ----------
        for acc in CLASS_ACCOUNTS:
            write_open(acc, content, f)

        f.write("\n; ====== Opening Balances ======\n\n")

        # ---------- opening balance transactions ----------
        for name, acc in ASSET_MAPPING.items():
            if opening_balance_exists(acc, content):
                continue

            balance = prompt_balance(acc, name)

            f.write(f"{OPEN_DATE} * \"Opening Balance\"\n")
            f.write(f"  {acc}  {balance} {CURRENCY}\n")
            f.write(f"  {EQUITY_ACCOUNT}\n\n")

    print("\n✅ main.beancount 初始化完成")


if __name__ == "__main__":
    init_beancount()
