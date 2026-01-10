import sys
import pandas as pd
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import re
import io
from typing import List, Dict, Optional

sys.dont_write_bytecode = True

# Try to import PDF parsing library
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    print("警告: PyPDF2 未安装，PDF解析功能将不可用。请运行 'pip install PyPDF2' 安装。")

def is_bank_file(file_path: Path) -> bool:
    """
    判断是否为银行账单：
    1. 文件扩展名为 .pdf 或 .xlsx/.xls
    2. 文件名包含银行相关关键词
    """
    filename = file_path.name.lower()

    # 检查文件扩展名
    if file_path.suffix.lower() not in ['.pdf', '.xlsx', '.xls']:
        return False

    # 银行关键词（排除通用词如"账单"，使用更具体的银行名称）
    bank_keywords = [
        "bank", "statement", "流水", "account",
        "icbc", "cmb", "ccb", "boc", "abc", "中国银行", "建设银行",
        "工商银行", "农业银行", "招商银行", "交通银行", "浦发银行",
        "中信银行", "光大银行", "华夏银行", "民生银行", "平安银行",
        "兴业银行", "广发银行", "邮储银行"
 ]

    # 检查文件名是否包含银行关键词
    for kw in bank_keywords:
        if kw.lower() in filename:
            return True

    # 如果文件名不包含关键词，尝试检查文件内容（仅对Excel文件）
    if file_path.suffix.lower() in ['.xlsx', '.xls']:
        try:
            df = pd.read_excel(file_path, dtype=str, nrows=20)  # 只读取前20行检查
            # 检查是否包含银行账单常见的列名
            common_headers = ["交易日期", "交易时间", "日期", "时间", "金额", "余额",
                            "交易类型", "摘要", "交易流水号", "account", "date",
                            "amount", "balance", "type", "description"]

            for col in df.columns:
                col_str = str(col).lower()
                for header in common_headers:
                    if header in col_str:
                        return True
        except Exception:
            pass  # 如果无法读取Excel文件，则返回False

    # 对PDF文件，检查是否包含银行账单关键词
    elif file_path.suffix.lower() == '.pdf':
        if PDF_AVAILABLE:
            try:
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    # 检查前几页内容
                    num_pages = min(3, len(pdf_reader.pages))
                    for i in range(num_pages):
                        page = pdf_reader.pages[i]
                        text = page.extract_text()
                        # 检查是否包含银行账单关键词
                        bank_statement_keywords = ["银行", "账户", "流水", "交易", "余额",
                                                 "银行账单", "account statement",
                                                 "transaction", "balance"]
                        for keyword in bank_statement_keywords:
                            if keyword in text:
                                return True
            except Exception:
                pass  # 如果无法读取PDF文件，则返回False
        else:
            print(f"无法检查PDF文件内容: {file_path.name} (缺少PyPDF2库)")

    return False

def parse_pdf_bank(file_path: Path) -> List[Dict]:
    """
    解析PDF格式的银行账单

    Args:
        file_path: PDF文件路径

    Returns:
        List[Dict]: 交易记录列表
    """
    if not PDF_AVAILABLE:
        print("错误: 无法解析PDF文件，缺少PyPDF2库")
        return []

    transactions = []

    try:
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)

            # 银行账单常见的中文关键词
            date_patterns = [
                r'\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?',  # 2023年1月1日, 2023/1/1, 2023-01-01
                r'\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日\s]',  # 包含日期的其他格式
            ]

            amount_patterns = [
                r'[\d,]+\.?\d*',  # 数字金额
            ]

            # 遍历每一页
            for page_num, page in enumerate(pdf_reader.pages):
                try:
                    text = page.extract_text()

                    # 按行分割文本
                    lines = text.split('\n')

                    for line in lines:
                        # 尝试从行中提取交易信息
                        # 这里需要根据实际银行账单格式进行调整
                        # 以下是一个通用的解析方法
                        line = line.strip()

                        # 查找可能包含交易信息的行
                        # 通常包含日期和金额
                        for date_pattern in date_patterns:
                            date_match = re.search(date_pattern, line)
                            if date_match:
                                # 在同一行中查找金额
                                for amount_pattern in amount_patterns:
                                    # 查找正数金额（支出）或负数金额（收入）
                                    amount_matches = re.findall(r'-?[\d,]+\.?\d+', line)
                                    if amount_matches:
                                        # 提取第一个找到的金额
                                        amount_str = amount_matches[0].replace(',', '')
                                        try:
                                            amount = Decimal(amount_str)
                                            date_str = date_match.group()

                                            # 解析日期
                                            date_obj = parse_date_string(date_str)
                                            if date_obj:
                                                # 提取交易对方或摘要信息（通常在日期和金额附近）
                                                # 这里需要根据实际银行账单格式进行调整
                                                # 简化处理：提取日期和金额之间的文本作为交易对方
                                                parts = re.split(r'[\d,]+\.?\d+', line)
                                                payee = ""
                                                if len(parts) > 0:
                                                    # 在日期后，金额前的部分可能是交易对方
                                                    date_pos = line.find(date_str)
                                                    amount_pos = line.find(amount_matches[0])
                                                    if date_pos >= 0 and amount_pos >= 0:
                                                        payee = line[date_pos + len(date_str):amount_pos].strip()

                                                # 如果没有找到交易对方，使用整行作为备注
                                                if not payee:
                                                    payee = "银行交易"

                                                transactions.append({
                                                    "date": date_obj,
                                                    "payee": payee,
                                                    "amount": abs(amount),  # 使用绝对值，方向由其他字段确定
                                                    "note": f"PDF页{page_num + 1}: {line}",
                                                    "raw_category": "银行交易",
                                                    "raw_account": "银行账户"
                                                })
                                        except ValueError:
                                            # 金额转换失败，跳过此行
                                            continue
                                        except Exception as e:
                                            print(f"处理金额时出错: {e}")
                                            continue
                                    break  # 只处理第一个找到的金额
                except Exception as e:
                    print(f"处理PDF页面 {page_num + 1} 时出错: {e}")
                    continue  # 继续处理下一页
    except FileNotFoundError:
        print(f"错误: 找不到PDF文件: {file_path}")
        return []
    except Exception as e:
        print(f"解析PDF文件时出错: {e}")
        return []

    return transactions

def parse_date_string(date_str: str) -> Optional[datetime.date]:
    """
    解析日期字符串

    Args:
        date_str: 日期字符串

    Returns:
        Optional[datetime.date]: 解析后的日期，如果失败则返回None
    """
    # 移除可能的中文字符并标准化格式
    date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '')

    try:
        # 尝试多种日期格式
        formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S'
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
    except:
        pass

    return None

def parse_xlsx_bank(file_path: Path) -> List[Dict]:
    """
    解析XLSX/XLS格式的银行账单

    Args:
        file_path: Excel文件路径

    Returns:
        List[Dict]: 交易记录列表
    """
    transactions = []

    try:
        # 读取Excel文件
        df = pd.read_excel(file_path, dtype=str)

        if df.empty:
            print(f"警告: Excel文件为空: {file_path.name}")
            return transactions

        # 尝试识别列名（支持中英文）
        date_cols = ['交易日期', '交易时间', '日期', '时间', 'date', 'transaction_date']
        amount_cols = ['金额', '交易金额', 'amount', 'transaction_amount']
        payee_cols = ['交易对方', '对方户名', '收款人', '付款人', 'payee', 'counterparty']
        note_cols = ['摘要', '备注', '说明', 'description', 'note']
        category_cols = ['交易类型', '业务类型', 'type', 'category']
        account_cols = ['账户', '卡号', 'account', 'card_number']

        # 查找实际的列名
        date_col = find_column_name(df, date_cols)
        amount_col = find_column_name(df, amount_cols)
        payee_col = find_column_name(df, payee_cols)
        note_col = find_column_name(df, note_cols)
        category_col = find_column_name(df, category_cols)
        account_col = find_column_name(df, account_cols)

        if not date_col or not amount_col:
            print(f"警告: 未找到日期或金额列，可能无法正确解析文件: {file_path.name}")
            return transactions

        # 遍历每一行数据
        for idx, row in df.iterrows():
            try:
                # 检查必要字段是否存在
                date_raw = row.get(date_col, "")
                if pd.isna(date_raw) or date_raw == "":
                    continue  # 跳过空行

                # 解析日期
                date_obj = parse_date_string(str(date_raw))
                if not date_obj:
                    continue  # 日期解析失败，跳过此行

                # 解析金额
                amount_raw = str(row.get(amount_col, "")).replace("¥", "").replace(",", "").replace(" ", "")
                if amount_raw == "":
                    continue  # 金额为空，跳过此行

                try:
                    # 处理正负号，银行流水可能有正负号表示收入/支出
                    amount = Decimal(amount_raw)
                except ValueError:
                    print(f"警告: 第{idx+1}行金额格式错误: {amount_raw}")
                    continue  # 金额转换失败，跳过此行

                # 获取交易对方
                payee = str(row.get(payee_col, "")).strip() if payee_col else "银行交易"

                # 获取备注
                note = str(row.get(note_col, "")).strip() if note_col else ""

                # 获取交易类型
                category = str(row.get(category_col, "")).strip() if category_col else "银行交易"

                # 获取账户信息
                account = str(row.get(account_col, "")).strip() if account_col else "银行账户"

                # 添加到交易列表
                transactions.append({
                    "date": date_obj,
                    "payee": payee,
                    "amount": abs(amount),  # 使用绝对值，方向由其他字段确定
                    "note": note,
                    "raw_category": category,
                    "raw_account": account
                })
            except KeyError as e:
                print(f"警告: 第{idx+1}行数据格式错误，跳过该行: {e}")
                continue
            except Exception as e:
                print(f"警告: 处理第{idx+1}行时出错，跳过该行: {e}")
                continue

    except FileNotFoundError:
        print(f"错误: 找不到Excel文件: {file_path}")
        return []
    except pd.errors.EmptyDataError:
        print(f"错误: Excel文件数据为空: {file_path}")
        return []
    except Exception as e:
        print(f"解析Excel文件时出错: {e}")
        return []

    return transactions

def find_column_name(df, possible_names):
    """
    在DataFrame中查找匹配的列名

    Args:
        df: DataFrame
        possible_names: 可能的列名列表

    Returns:
        str or None: 找到的列名，如果没找到则返回None
    """
    for col in df.columns:
        col_str = str(col).strip()
        for name in possible_names:
            if name.lower() in col_str.lower():
                return col
    return None

def parse_bank(file_path: Path) -> List[Dict]:
    """
    解析银行账单主函数

    Args:
        file_path: 银行账单文件路径（PDF或Excel格式）

    Returns:
        List[Dict]: 交易记录列表
    """
    print(f"   [系统] 开始解析银行账单: {file_path.name}")

    # 检查文件是否存在
    if not file_path.exists():
        print(f"   [错误] 文件不存在: {file_path}")
        return []

    # 根据文件扩展名选择解析方法
    try:
        if file_path.suffix.lower() == '.pdf':
            return parse_pdf_bank(file_path)
        elif file_path.suffix.lower() in ['.xlsx', '.xls']:
            return parse_xlsx_bank(file_path)
        else:
            print(f"   [错误] 不支持的文件格式: {file_path.suffix}")
            return []
    except Exception as e:
        print(f"   [错误] 解析文件时发生未知错误: {e}")
        return []