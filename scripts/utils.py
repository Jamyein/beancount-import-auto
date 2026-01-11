"""
公共工具函数模块

提供跨导入器共享的工具函数
"""
import csv
import io
from pathlib import Path
from typing import List, Dict, Optional
from decimal import Decimal

from logger_config import get_logger

logger = get_logger(__name__)


# 支付宝表头常量
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

# 成功交易状态关键词
SUCCESS_STATUS_KEYWORDS = ["成功", "已收", "已转", "已送出", "支付成功", "收款成功", "交易完成"]

# 银行关键词
BANK_KEYWORDS = [
    "bank", "statement", "流水", "account",
    "icbc", "cmb", "ccb", "boc", "abc",
    "中国银行", "建设银行", "工商银行", "农业银行",
    "招商银行", "交通银行", "浦发银行", "中信银行",
    "光大银行", "华夏银行", "民生银行", "平安银行",
    "兴业银行", "广发银行", "邮储银行"
]

# 微信关键词
WECHAT_KEYWORDS = ["微信", "wechat"]

# 支付宝关键词（增强版）
ALIPAY_KEYWORDS = [
    "支付宝", "alipay", "ali-pay", "zhifubao",
    "alipay_bill", "zfb", "支付宝账单",
    "alipay_export", "支付宝导出", "ali_export"
]


def detect_file_by_keywords(
    file_path: Path,
    keywords: List[str]
) -> bool:
    """通过文件名关键词检测文件类型

    Args:
        file_path: 文件路径
        keywords: 关键词列表

    Returns:
        是否匹配
    """
    filename = file_path.name.lower()
    return any(kw.lower() in filename for kw in keywords)


def find_header_line(
    lines: List[str],
    keywords: List[str],
    max_lines: int = 20
) -> Optional[int]:
    """在行列表中查找包含关键词的表头行

    Args:
        lines: 行列表
        keywords: 要查找的关键词
        max_lines: 最大查找行数

    Returns:
        表头行索引，未找到返回 None
    """
    for i, line in enumerate(lines):
        if i >= max_lines:
            break
        if all(keyword in line for keyword in keywords):
            return i
    return None


def load_csv_with_encoding(
    file_path: Path,
    encodings: Optional[List[str]] = None,
    skip_lines: int = 0
) -> List[Dict[str, str]]:
    """自动检测编码并加载CSV文件

    Args:
        file_path: CSV文件路径
        encodings: 尝试的编码列表
        skip_lines: 跳过的行数

    Returns:
        CSV行数据列表

    Raises:
        IOError: 文件读取失败
        UnicodeDecodeError: 所有编码都失败
    """
    if encodings is None:
        encodings = ['gbk', 'gb18030', 'utf-8', 'utf-8-sig']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                if skip_lines > 0:
                    for _ in range(skip_lines):
                        next(f, None)
                reader = csv.DictReader(f)
                return [row for row in reader]
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.debug(f"使用编码 {encoding} 读取失败: {e}")
            continue

    raise UnicodeDecodeError(
        f"无法使用任何编码读取文件: {encodings}"
    )


def parse_csv_from_text(
    text: str
) -> List[Dict[str, str]]:
    """从文本内容解析CSV

    Args:
        text: CSV文本内容

    Returns:
        CSV行数据列表
    """
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader]


def normalize_dict_keys(d: Dict[str, str]) -> Dict[str, str]:
    """标准化字典键名（去除前后空格，过滤空键）

    Args:
        d: 输入字典

    Returns:
        标准化后的字典
    """
    return {k.strip(): v.strip() for k, v in d.items() if k}


def validate_success_status(status: str) -> bool:
    """验证交易状态是否为成功

    Args:
        status: 交易状态字符串

    Returns:
        是否为成功状态
    """
    status = status.strip()
    return any(keyword in status for keyword in SUCCESS_STATUS_KEYWORDS)


def clean_amount_string(amount_str: str) -> str:
    """清理金额字符串（移除符号和空格）

    Args:
        amount_str: 原始金额字符串

    Returns:
        清理后的金额字符串
    """
    return (amount_str
            .replace("¥", "")
            .replace("￥", "")
            .replace("$", "")
            .replace(" ", "")
            .replace(",", "")
            .strip())


def detect_asset_account(
    raw_account: str,
    asset_mapping: Dict[str, str]
) -> str:
    """根据支付方式识别资产账户

    Args:
        raw_account: 原始账户信息
        asset_mapping: 资产账户映射配置

    Returns:
        识别到的资产账户，无法识别返回 "Assets:FixMe"
    """
    if not raw_account:
        return "Assets:FixMe"

    for keyword, account in asset_mapping.items():
        if keyword.lower() in raw_account.lower():
            return account

    return "Assets:FixMe"


def format_beancount_entry(
    date,
    payee: str,
    expense_account: str,
    asset_account: str,
    amount: Decimal
) -> str:
    """格式化 Beancount 分录

    Args:
        date: 交易日期
        payee: 交易对方
        expense_account: 支出账户
        asset_account: 资产账户
        amount: 金额

    Returns:
        Beancount 分录字符串
    """
    # 转义双引号
    payee_escaped = payee.replace('"', '""')

    entry = (
        f'{date} * "{payee_escaped}"\n'
        f'  {expense_account}  {amount} CNY\n'
        f'  {asset_account}\n\n'
    )
    return entry


def ensure_directory(file_path: Path) -> None:
    """确保目录存在

    Args:
        file_path: 文件路径

    Raises:
        OSError: 目录创建失败
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"创建目录失败: {e}")
        raise


def is_empty_row(row: Dict[str, str]) -> bool:
    """检查数据行是否为空

    Args:
        row: 数据行

    Returns:
        是否为空行
    """
    import pandas as pd

    for value in row.values():
        if value and not pd.isna(value):
            return False
    return True


def find_column_name(
    columns,
    possible_names: List[str]
) -> Optional[str]:
    """在列名列表中查找匹配的列

    Args:
        columns: 列名列表
        possible_names: 可能的列名列表

    Returns:
        找到的列名，未找到返回 None
    """
    for col in columns:
        col_str = str(col).strip()
        for name in possible_names:
            if name in col_str:
                return col
    return None
