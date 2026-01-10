import sys
import pandas as pd
from decimal import Decimal
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True

def is_wechat_file(file_path: Path) -> bool:
    filename = file_path.name.lower()
    return "微信" in filename or "wechat" in filename

def parse_wechat(file_path: Path):
    # 使用 pandas 读取 Excel
    try:
        # 微信 Excel 账单头部通常有几行统计信息，先读入 DataFrame
        df_raw = pd.read_excel(file_path, dtype=str)
    except Exception as e:
        print(f"   [错误] 无法读取 Excel 文件: {e}")
        return []

    # 1. 定位标题行（寻找包含“交易时间”的那一行作为表头）
    header_row_index = -1
    for i, row in df_raw.iterrows():
        if "交易时间" in row.values:
            header_row_index = i
            break
    
    if header_row_index == -1:
        print("   [错误] 未能在 Excel 中找到“交易时间”列，请确认文件是否为微信导出的账单。")
        return []

    # 2. 重新读取数据，跳过标题行之前的说明文字
    df = pd.read_excel(file_path, skiprows=header_row_index + 1)
    
    # 清理列名（去除首尾空格）
    df.columns = [str(c).strip() for c in df.columns]

    transactions = []
    
    for _, row in df.iterrows():
        # 过滤掉金额或时间为空的行（通常是底部的统计行）
        if pd.isna(row.get("金额(元)")) or pd.isna(row.get("交易时间")):
            continue
        
        # 状态过滤：只处理支付成功、已转账、已收钱等成功状态
        status = str(row.get("当前状态", "")).strip()
        # 常见成功状态关键词
        success_keywords = ["成功", "已收", "已转", "已送出"]
        if not any(kw in status for kw in success_keywords):
            continue

        # 处理金额：去除人民币符号、逗号，转为 Decimal
        amount_raw = str(row.get("金额(元)")).replace("¥", "").replace(",", "").strip()
        try:
            amount = Decimal(amount_raw)
        except:
            continue
        
        # 处理日期：Excel 可能会将其读取为 datetime 对象或字符串
        date_raw = str(row.get("交易时间")).strip()
        try:
            # pd.to_datetime 能自动识别多种日期格式
            date_obj = pd.to_datetime(date_raw)
            date = date_obj.date()
        except:
            continue

        # 封装为字典，字段名需与 importer_main.py 保持一致
        transactions.append({
            "date": date,
            "payee": str(row.get("交易对方", "")).strip(),
            "amount": amount,
            "note": str(row.get("商品", "")).strip(),
            "raw_category": str(row.get("交易类型", "")).strip(),
            "raw_account": str(row.get("支付方式", "")).strip()
        })
    
    return transactions