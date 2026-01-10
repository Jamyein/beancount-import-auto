# scripts/importer_alipay.py
import sys
import csv
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from dateutil import parser as date_parser

sys.dont_write_bytecode = True

ALIPAY_HEADER = [
    "记录时间",
    "交易号",
    "交易对方",
    "收/支",
    "金额",
    "来源",
    "备注",
    "标签",
]


def is_alipay_file(file_path: Path) -> bool:
    """
    判断是否为支付宝账单：
    1. 文件名包含支付宝 / alipay 等关键词
    2. 或第25行包含支付宝标准表头
    """

    filename = file_path.name.lower()

    name_keywords = [
        "支付宝",
        "alipay",
        "ali-pay",
        "zhifubao",
    ]

    # ---------- 1️⃣ 文件名快速判断 ----------
    for kw in name_keywords:
        if kw.lower() in filename:
            return True

    # ---------- 2️⃣ 表头兜底判断 ----------
    try:
        with open(file_path, "r", encoding="gbk") as f:
            for i, line in enumerate(f, start=1):
                if i <= 10:  # 在前10行内查找表头
                    return all(h in line for h in ALIPAY_HEADER)
    except Exception:
        return False

    return False


def parse_alipay(file_path: Path):
    transactions = []

    # 1. 确保使用 GBK 编码
    with open(file_path, "r", encoding="gbk") as f:
        lines = f.readlines()

    # 2. 找到真正的表头行 (包含 "交易时间" 或 "记录时间" 的那一行)
    header_index = 0
    for i, line in enumerate(lines):
        if "交易时间" in line or "记录时间" in line:
            header_index = i
            break
            
    # 3. 将分隔符改为逗号，并使用 strip() 处理可能的空格
    import io
    content = "".join(lines[header_index:])
    reader = csv.DictReader(io.StringIO(content)) 

    for row in reader:
        # 去掉 key 和 value 的前后空格
        row = {k.strip(): v.strip() for k, v in row.items() if k}
        
        # 如果是空行或不包含金额，跳过
        if not row.get("金额"):
            continue

        # 4. 优化状态判断逻辑，防止因为细微差异漏掉数据
        status = row.get("交易状态", "")
        if "成功" not in status and "已收" not in status:
            continue

        # ... 下方解析逻辑保持不变，但确保 key 对应正确 ...
        date = date_parser.parse(row["交易时间"]).date()
        amount = Decimal(row["金额"])


        direction = "out" if row["收/支"] == "支出" else "in"

        tx = {
            "date": date,
            "payee": row.get("交易对方", "").strip(),
            "note": row.get("商品说明", "").strip() or row.get("备注", "").strip(),
            "amount": amount,
            "currency": "CNY",
            "direction": direction,
            "raw_category": row.get("标签", "").strip() or row.get("交易分类", "").strip(),
            "raw_account": row.get("来源", "").strip() or row.get("账户", "").strip() or row.get("收/付款方式", "").strip(),
            "source": "alipay",
            "narration": row.get("备注", "").strip(),
        }

        transactions.append(tx)

    return transactions

