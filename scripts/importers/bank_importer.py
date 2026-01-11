"""
银行账单导入器模块

重构版本：继承 BaseImporter，支持 PDF 和 Excel 格式
"""
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re
from datetime import datetime

import pandas as pd

from base_importer import BaseImporter, Transaction, ImportRegistry
from utils import (
    BANK_KEYWORDS,
    detect_file_by_keywords,
    find_column_name,
    normalize_dict_keys,
    validate_success_status,
)
from logger_config import get_logger

logger = get_logger(__name__)

# PDF 解析可用性标记
try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("PyPDF2 未安装，PDF 解析功能不可用。请运行 'pip install PyPDF2' 安装。")


class BankImporter(BaseImporter):
    """银行账单导入器

    支持格式：
        - PDF 格式（需要 PyPDF2）
        - XLSX/XLS 格式（Excel）

    表头格式：
        - 日期列：交易日期、交易时间、日期、时间
        - 金额列：金额、交易金额
        - 对方列：交易对方、对方户名
        - 备注列：摘要、备注
        - 类型列：交易类型、业务类型
    """

    PLATFORM_NAME = "Bank"
    SUPPORTED_EXTENSIONS = ['.pdf', '.xlsx', '.xls']

    # 列名映射配置
    COLUMN_MAPPINGS = {
        "date": ["交易日期", "交易时间", "日期", "时间", "date", "transaction_date"],
        "amount": ["金额", "交易金额", "amount", "transaction_amount"],
        "payee": ["交易对方", "对方户名", "收款人", "付款人", "payee", "counterparty"],
        "note": ["摘要", "备注", "说明", "description", "note"],
        "category": ["交易类型", "业务类型", "type", "category"],
        "account": ["账户", "卡号", "account", "card_number"],
        "status": ["交易状态", "状态", "status"]
    }

    # PDF 解析参数
    PDF_MAX_PAGES = 3  # 只检查前几页

    def supports_file(self, path: Path) -> bool:
        """判断是否为银行账单

        Args:
            path: 文件路径

        Returns:
            是否支持该文件
        """
        # 扩展名校验
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False

        # 文件名关键词检查
        if detect_file_by_keywords(path, BANK_KEYWORDS):
            self.logger.debug(f"通过文件名识别: {path.name}")
            return True

        # 内容检查
        if path.suffix.lower() in ['.xlsx', '.xls']:
            return self._check_excel_content(path)
        elif path.suffix.lower() == '.pdf':
            return self._check_pdf_content(path)

        return False

    def _check_excel_content(self, path: Path) -> bool:
        """检查 Excel 文件内容

        Args:
            path: 文件路径

        Returns:
            是否为有效的银行账单
        """
        try:
            df = pd.read_excel(path, dtype=str, nrows=20)
            df.columns = [str(c).strip() for c in df.columns]

            # 检查是否包含银行账单常见的列名
            key_columns = self.COLUMN_MAPPINGS["date"] + self.COLUMN_MAPPINGS["amount"]
            return any(col in df.columns for col in key_columns)

        except Exception as e:
            self.logger.debug(f"Excel 内容检查失败: {e}")
            return False

    def _check_pdf_content(self, path: Path) -> bool:
        """检查 PDF 文件内容

        Args:
            path: 文件路径

        Returns:
            是否为有效的银行账单
        """
        if not PDF_AVAILABLE:
            self.logger.warning("PDF 解析功能不可用")
            return False

        try:
            with open(path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = min(self.PDF_MAX_PAGES, len(pdf_reader.pages))

                # 检查是否包含银行账单关键词
                keywords = ["银行", "账户", "流水", "交易", "余额",
                           "银行账单", "account statement",
                           "transaction", "balance"]

                for i in range(num_pages):
                    page = pdf_reader.pages[i]
                    text = page.extract_text()

                    for keyword in keywords:
                        if keyword in text:
                            self.logger.debug(f"通过 PDF 内容识别: {path.name}")
                            return True

            return False

        except Exception as e:
            self.logger.debug(f"PDF 内容检查失败: {e}")
            return False

    def extract_transactions(self, path: Path) -> List[Transaction]:
        """提取银行交易记录

        Args:
            path: 文件路径

        Returns:
            交易记录列表

        Raises:
            FileFormatError: 文件格式不正确
            ImportError: 导入过程失败
        """
        try:
            # 验证文件大小
            self.validate_file_size(path)

            # 根据扩展名选择解析方法
            if path.suffix.lower() == '.pdf':
                if not PDF_AVAILABLE:
                    raise ImportError("PDF 解析功能不可用，请安装 PyPDF2")
                transactions = self._parse_pdf(path)
            elif path.suffix.lower() in ['.xlsx', '.xls']:
                transactions = self._parse_excel(path)
            else:
                raise FileFormatError(f"不支持的文件格式: {path.suffix}")

            self.logger.info(f"成功解析 {len(transactions)} 条银行交易")
            return transactions

        except ImportError:
            raise
        except Exception as e:
            self.logger.error(f"解析银行账单失败: {path} - {e}")
            raise ImportError(f"银行账单解析失败: {e}") from e

    def _parse_excel(self, path: Path) -> List[Transaction]:
        """解析 Excel 格式银行账单

        Args:
            path: Excel 文件路径

        Returns:
            交易记录列表
        """
        try:
            df = pd.read_excel(path, dtype=str)

            if df.empty:
                self.logger.warning(f"Excel 文件为空: {path.name}")
                return []

            # 清理列名
            df.columns = [str(c).strip() for c in df.columns]

            # 预先查找各列
            date_col = find_column_name(df, self.COLUMN_MAPPINGS["date"])
            amount_col = find_column_name(df, self.COLUMN_MAPPINGS["amount"])
            payee_col = find_column_name(df, self.COLUMN_MAPPINGS["payee"])
            note_col = find_column_name(df, self.COLUMN_MAPPINGS["note"])
            category_col = find_column_name(df, self.COLUMN_MAPPINGS["category"])
            account_col = find_column_name(df, self.COLUMN_MAPPINGS["account"])

            # 验证必需列
            if not date_col or not amount_col:
                self.logger.warning(
                    f"未找到日期或金额列: {path.name}"
                )
                return []

            self.logger.debug(
                f"列映射: date={date_col}, amount={amount_col}, "
                f"payee={payee_col}"
            )

            # 解析交易
            transactions = self._parse_dataframe(
                df,
                date_col=date_col,
                amount_col=amount_col,
                payee_col=payee_col,
                note_col=note_col,
                category_col=category_col,
                account_col=account_col
            )

            return transactions

        except Exception as e:
            self.logger.error(f"解析 Excel 文件失败: {path} - {e}")
            raise ImportError(f"Excel 解析失败: {e}") from e

    def _parse_dataframe(
        self,
        df: pd.DataFrame,
        date_col: str,
        amount_col: str,
        payee_col: Optional[str] = None,
        note_col: Optional[str] = None,
        category_col: Optional[str] = None,
        account_col: Optional[str] = None
    ) -> List[Transaction]:
        """解析 DataFrame 提取交易记录

        Args:
            df: pandas DataFrame
            date_col: 日期列名
            amount_col: 金额列名
            payee_col: 对方列名
            note_col: 备注列名
            category_col: 类型列名
            account_col: 账户列名

        Returns:
            交易记录列表
        """
        transactions = []
        skipped_count = 0

        for idx, row in df.iterrows():
            try:
                # 检查必要字段是否存在
                date_raw = row.get(date_col, "")
                if pd.isna(date_raw) or str(date_raw).strip() == "":
                    skipped_count += 1
                    continue

                # 解析日期
                date = self.parse_date(str(date_raw), idx + 2)
                if not date:
                    skipped_count += 1
                    continue

                # 解析金额
                amount_raw = str(row.get(amount_col, "")).replace("¥", "").replace(",", "")
                if str(amount_raw).strip() == "":
                    skipped_count += 1
                    continue

                try:
                    amount = self.parse_amount(amount_raw, idx + 2)
                except Exception:
                    self.logger.warning(f"第{idx+2}行金额格式错误: {amount_raw}")
                    skipped_count += 1
                    continue

                # 获取其他字段
                payee = self.safe_get(row.get(payee_col), "银行交易")
                note = self.safe_get(row.get(note_col), "")
                raw_category = self.safe_get(row.get(category_col), "银行交易")
                raw_account = self.safe_get(row.get(account_col), "银行账户")

                # 转义字符串中的特殊字符
                payee = self.escape_beancount_string(payee)
                note = self.escape_beancount_string(note)

                # 创建交易对象
                tx = Transaction(
                    date=date,
                    payee=payee,
                    amount=amount,
                    raw_category=raw_category,
                    raw_account=raw_account,
                    note=note,
                    source="bank",
                    status="success"
                )

                # 验证交易
                self.validate_transaction(tx)
                transactions.append(tx)

            except Exception as e:
                self.logger.warning(f"第{idx+2}行处理失败: {e}，已跳过")
                skipped_count += 1
                continue

        if skipped_count > 0:
            self.logger.info(f"跳过 {skipped_count} 条无效记录")

        return transactions

    def _parse_pdf(self, path: Path) -> List[Transaction]:
        """解析 PDF 格式银行账单

        Args:
            path: PDF 文件路径

        Returns:
            交易记录列表

        Raises:
            ImportError: PDF 解析失败
        """
        if not PDF_AVAILABLE:
            raise ImportError("PDF 解析功能不可用，请安装 PyPDF2")

        transactions = []

        try:
            with open(path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                num_pages = min(self.PDF_MAX_PAGES, len(pdf_reader.pages))

                # 日期正则表达式
                date_patterns = [
                    r'\d{4}[年/-]\d{1,2}[月/-]\d{1,2}日?',
                    r'\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日\s]',
                ]

                # 金额正则表达式
                amount_pattern = r'-?[\d,]+\.?\d*'

                for page_num in range(num_pages):
                    try:
                        page = pdf_reader.pages[page_num]
                        text = page.extract_text()

                        # 按行分割
                        lines = text.split('\n')

                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue

                            # 尝试解析交易信息
                            tx = self._parse_pdf_line(
                                line=line,
                                page_num=page_num,
                                date_patterns=date_patterns,
                                amount_pattern=amount_pattern
                            )

                            if tx:
                                transactions.append(tx)

                    except Exception as e:
                        self.logger.warning(f"处理 PDF 第 {page_num + 1} 页时出错: {e}")
                        continue

                return transactions

        except FileNotFoundError:
            raise ImportError(f"PDF 文件不存在: {path}")
        except Exception as e:
            self.logger.error(f"解析 PDF 文件失败: {path} - {e}")
            raise ImportError(f"PDF 解析失败: {e}") from e

    def _parse_pdf_line(
        self,
        line: str,
        page_num: int,
        date_patterns: List[str],
        amount_pattern: str
    ) -> Optional[Transaction]:
        """从单行 PDF 文本解析交易信息

        Args:
            line: 文本行
            page_num: 页码
            date_patterns: 日期正则列表
            amount_pattern: 金额正则

        Returns:
            交易记录，解析失败返回 None
        """
        # 查找日期
        date_match = None
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                date_match = match
                break

        if not date_match:
            return None

        # 在同一行中查找金额
        amount_matches = re.findall(r'-?[\d,]+\.?\d*', line)
        if not amount_matches:
            return None

        # 提取第一个金额
        amount_str = amount_matches[0].replace(',', '')

        try:
            amount = self.parse_amount(amount_str)
            date_str = date_match.group()
            date = self.parse_date(date_str)

            if not date:
                return None

            # 提取交易对方（日期和金额之间的文本）
            date_pos = line.find(date_str)
            amount_pos = line.find(amount_matches[0])

            if date_pos >= 0 and amount_pos >= 0 and amount_pos > date_pos:
                payee = line[date_pos + len(date_str):amount_pos].strip()
            else:
                payee = "银行交易"

            if not payee:
                payee = "银行交易"

            # 转义
            payee = self.escape_beancount_string(payee)

            return Transaction(
                date=date,
                payee=payee,
                amount=amount,
                raw_category="银行交易",
                raw_account="银行账户",
                note=f"PDF 第 {page_num + 1} 页",
                source="bank",
                status="success"
            )

        except Exception as e:
            self.logger.debug(f"解析 PDF 行失败: {e}")
            return None


# 自动注册到全局注册表
from base_importer import registry
registry.register(BankImporter)
