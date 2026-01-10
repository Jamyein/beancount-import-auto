import sys
import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

# 导入自定义模块
from importer_alipay import is_alipay_file, parse_alipay
from importer_wechat import is_wechat_file, parse_wechat
from importer_bank import is_bank_file, parse_bank
from memory_brain import MemoryBrain

# ---------- 初始化配置 ----------
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.json"

def load_config() -> Dict:
    """
    从配置文件加载配置

    Returns:
        Dict: 配置字典
    """
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

# 资产映射与目录配置
ASSET_MAPPING = config.get("asset_mapping", {})
MONTHLY_DIR_NAME = config.get('monthly_dir', 'data')
MONTHLY_DIR = BASE_DIR / MONTHLY_DIR_NAME
MAIN_LEDGER = BASE_DIR / config.get("main_bean_file", "main.beancount")

brain = MemoryBrain()

# ---------- 工具函数 ----------

def ensure_dir(file_path: str) -> None:
    """
    确保目标文件的目录存在

    Args:
        file_path: 文件路径
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    except OSError as e:
        print(f"   [错误] 创建目录失败: {e}")
        raise

def detect_asset_account(raw_account: str) -> str:
    """
    根据账单支付方式识别资产账户

    Args:
        raw_account: 原始账户信息

    Returns:
        str: 识别到的资产账户，如果无法识别则返回"Assets:FixMe"
    """
    if not raw_account:
        return "Assets:FixMe"
    for keyword, account in ASSET_MAPPING.items():
        if keyword.lower() in raw_account.lower():
            return account
    return "Assets:FixMe"

def update_main_ledger(rel_path: str) -> None:
    """
    在主账本中追加 include 语句

    Args:
        rel_path: 相对路径
    """
    # 统一路径格式为斜杠，适配 Beancount 语法
    formatted_path = rel_path.replace('\\', '/')
    include_line = f'include "{formatted_path}"'

    try:
        content = ""
        if MAIN_LEDGER.exists():
            content = MAIN_LEDGER.read_text(encoding="utf-8")

        if include_line not in content:
            with open(MAIN_LEDGER, "a", encoding="utf-8") as f:
                if content and not content.endswith('\n'):
                    f.write("\n")
                f.write(f"{include_line}\n")
            print(f"   [系统] 🔗 已在主账本中关联新文件: {formatted_path}")
    except IOError as e:
        print(f"   [错误] 更新主账本失败: {e}")
        raise

# ---------- 主逻辑 ----------

def process_transaction(tx: Dict) -> Tuple[str, str]:
    """
    处理单个交易并返回资产账户和分录字符串

    Args:
        tx: 交易字典

    Returns:
        Tuple[str, str]: 资产账户和分录字符串
    """
    # 获取资产账户（根据支付方式列识别）
    asset_account = detect_asset_account(tx["raw_account"])

    # 获取支出账户（通过 brain.classify 触发 AI 建议与人工确认）
    expense_account = brain.classify(
        payee=tx["payee"],
        raw_category=tx["raw_category"],
        note=tx["note"],
        raw_account=tx["raw_account"]
    )

    # 构造 Beancount 分录字符串
    entry_str = (
        f'{tx["date"]} * "{tx["payee"]}"\n'
        f'  {expense_account}  {tx["amount"]} CNY\n'
        f'  {asset_account}\n\n'
    )

    return asset_account, entry_str

def main(csv_file: str) -> bool:
    """
    主函数：处理CSV文件并导入到beancount账本

    Args:
        csv_file: CSV文件路径

    Returns:
        bool: 导入是否成功
    """
    file_path = Path(csv_file)
    txs = []

    # 1. 识别并解析文件
    try:
        if is_alipay_file(file_path):
            print(f"   [系统] 识别为支付宝账单: {file_path.name}")
            txs = parse_alipay(file_path)
        elif is_wechat_file(file_path):
            print(f"   [系统] 识别为微信账单: {file_path.name}")
            txs = parse_wechat(file_path)
        elif is_bank_file(file_path):
            print(f"   [系统] 识别为银行账单: {file_path.name}")
            txs = parse_bank(file_path)
        else:
            print(f"   [系统] 无法识别账单类型: {file_path.name}")
            return False
    except Exception as e:
        print(f"   [错误] 解析文件失败: {e}")
        return False

    if not txs:
        print("   [系统] 未找到有效数据或解析结果为空。")
        return False

    # 2. 准备容器
    entries_by_month: Dict[str, List[str]] = {}  # 格式: {"202512": ["entry1...", "entry2..."]}
    total_count = 0

    print(f"   [系统] 共解析到 {len(txs)} 条交易。")
    print("--------------------------------------------------")

    # 3. 遍历交易（此处包含人工确认步骤）
    for tx in txs:
        try:
            # 处理交易
            _, entry_str = process_transaction(tx)

            # 按月份分组存储
            month_key = tx["date"].strftime("%Y%m")
            if month_key not in entries_by_month:
                entries_by_month[month_key] = []

            entries_by_month[month_key].append(entry_str)
            total_count += 1
        except KeyError as e:
            print(f"   [错误] 交易数据格式错误，跳过该条记录: {e}")
            continue
        except Exception as e:
            print(f"   [错误] 处理交易时出错，跳过该条记录: {e}")
            continue

    print("--------------------------------------------------")
    # 4. 执行批量写入逻辑
    if entries_by_month:
        for month, entries in entries_by_month.items():
            # 确定分卷文件路径 (例如: data/202512.beancount)
            target_file = os.path.join(MONTHLY_DIR, f"{month}.beancount")
            ensure_dir(target_file)

            # 追加写入月份文件
            try:
                with open(target_file, 'a', encoding='utf-8') as f:
                    f.writelines(entries)
            except IOError as e:
                print(f"   [错误] 写入文件失败: {e}")
                continue

            # 构造相对路径用于 include
            rel_path = os.path.join(MONTHLY_DIR_NAME, f"{month}.beancount")
            update_main_ledger(rel_path)

        # 分类完成后统一保存 AI 映射缓存（mapping.json）
        try:
            brain._save_mapping()
        except Exception as e:
            print(f"   [错误] 保存AI映射缓存失败: {e}")

        print(f"   [完成] 成功导入 {total_count} 条数据，分布在 {len(entries_by_month)} 个文件中。")
        return True

    return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    args = parser.parse_args()
    main(args.file)