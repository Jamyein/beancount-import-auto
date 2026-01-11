"""
微信账单导入器模块

重构版本：继承 BaseImporter，提供统一的接口和健壮的错误处理
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd

from base_importer import BaseImporter, Transaction, ImportRegistry
from utils import (
    WECHAT_KEYWORDS,
    detect_file_by_keywords,
    validate_success_status,
    find_column_name,
)
from logger_config import get_logger

logger = get_logger(__name__)


class WeChatImporter(BaseImporter):
    """微信支付账单导入器

    支持格式：
        - XLSX/XLS 格式（Excel）
        - 文件名包含关键词自动识别

    表头格式：
        - 交易时间
        - 交易类型
        - 交易对方
        - 金额(元)
        - 支付方式
        - 当前状态
        - 商品
    """

    PLATFORM_NAME = "WeChat"
    SUPPORTED_EXTENSIONS = ['.xlsx', '.xls']
    ENCODING = 'utf-8'

    # 列名映射配置
    COLUMN_MAPPINGS = {
        "amount": ["金额(元)", "金额", "amount"],
        "date": ["交易时间", "时间", "交易日期", "date"],
        "payee": ["交易对方", "对方", "商户", "payee"],
        "note": ["商品", "商品说明", "备注", "note"],
        "category": ["交易类型", "类型", "category"],
        "account": ["支付方式", "收付款方式", "account"],
        "status": ["当前状态", "状态", "status"],
    }

    def supports_file(self, path: Path) -> bool:
        """判断是否为微信账单

        Args:
            path: 文件路径

        Returns:
            是否支持该文件
        """
        # 扩展名校验
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False

        # 文件名快速判断
        if detect_file_by_keywords(path, WECHAT_KEYWORDS):
            self.logger.debug(f"通过文件名识别: {path.name}")
            return True

        # 兜底检查：尝试读取Excel并检查表头
        return self._validate_content(path)

    def _validate_content(self, path: Path) -> bool:
        """验证文件内容是否包含微信账单特征

        Args:
            path: 文件路径

        Returns:
            是否为有效的微信账单
        """
        try:
            df = pd.read_excel(path, dtype=str, nrows=10)
            df.columns = [str(c).strip() for c in df.columns]

            # 检查是否包含关键列
            key_columns = ["交易时间", "金额(元)", "交易类型"]
            return any(col in df.columns for col in key_columns)

        except Exception as e:
            self.logger.debug(f"内容验证失败: {e}")
            return False

    def extract_transactions(self, path: Path) -> List[Transaction]:
        """提取微信交易记录

        Args:
            path: Excel 文件路径

        Returns:
            交易记录列表

        Raises:
            FileFormatError: 文件格式不正确
            ImportError: 导入过程失败
        """
        try:
            # 验证文件大小
            self.validate_file_size(path)

            # 定位表头行
            header_row_index = self._find_header_row(path)
            if header_row_index == -1:
                raise FileFormatError("未找到有效的表头行（包含 '交易时间'）")

            self.logger.debug(f"找到表头行: 第 {header_row_index + 1} 行")

            # 读取完整数据（跳过表头之前的行）
            df = pd.read_excel(
                path,
                skiprows=header_row_index + 1,
                dtype=str,
                engine='openpyxl'
            )

            # 清理列名
            df.columns = [str(c).strip() for c in df.columns]

            self.logger.debug(f"读取到 {len(df)} 行数据")

            # 解析交易
            transactions = self._parse_dataframe(df)

            self.logger.info(f"成功解析 {len(transactions)} 条微信交易")
            return transactions

        except ImportError as e:
            raise
        except Exception as e:
            self.logger.error(f"解析微信账单失败: {path} - {e}")
            raise ImportError(f"微信账单解析失败: {e}") from e

    def _find_header_row(self, path: Path) -> int:
        """查找包含 "交易时间" 的表头行

        Args:
            path: Excel 文件路径

        Returns:
            表头行索引（0-based），未找到返回 -1
        """
        try:
            df_raw = pd.read_excel(path, dtype=str, nrows=100)

            for i, row in df_raw.iterrows():
                if "交易时间" in row.values:
                    return i

            return -1

        except Exception as e:
            self.logger.warning(f"查找表头行失败: {e}")
            return -1

    def _parse_dataframe(self, df: pd.DataFrame) -> List[Transaction]:
        """解析 DataFrame 提取交易记录

        Args:
            df: pandas DataFrame

        Returns:
            交易记录列表
        """
        transactions = []
        skipped_count = 0

        # 预先查找各列
        amount_col = find_column_name(df, self.COLUMN_MAPPINGS["amount"])
        date_col = find_column_name(df, self.COLUMN_MAPPINGS["date"])
        status_col = find_column_name(df, self.COLUMN_MAPPINGS["status"])
        payee_col = find_column_name(df, self.COLUMN_MAPPINGS["payee"])
        note_col = find_column_name(df, self.COLUMN_MAPPINGS["note"])
        category_col = find_column_name(df, self.COLUMN_MAPPINGS["category"])
        account_col = find_column_name(df, self.COLUMN_MAPPINGS["account"])

        # 验证必需列
        if not amount_col or not date_col:
            raise FileFormatError(
                f"缺少必需列（需要: {self.COLUMN_MAPPINGS['amount']} 和 "
                f"{self.COLUMN_MAPPINGS['date']}）"
            )

        self.logger.debug(f"列映射: amount={amount_col}, date={date_col}")

        # 逐行解析
        for idx, row in df.iterrows():
            try:
                # 检查空行（金额或时间为空）
                if pd.isna(row.get(amount_col)) or pd.isna(row.get(date_col)):
                    skipped_count += 1
                    continue

                # 状态过滤（只处理成功的交易）
                if status_col:
                    status = str(row.get(status_col, ""))
                    if not validate_success_status(status):
                        self.logger.debug(f"跳过非成功状态: {status}")
                        skipped_count += 1
                        continue

                # 解析金额
                amount_raw = str(row.get(amount_col))
                amount = self.parse_amount(amount_raw, idx + 2)

                # 解析日期
                date_raw = str(row.get(date_col))
                date = self.parse_date(date_raw, idx + 2)

                # 获取其他字段
                payee = self.safe_get(row.get(payee_col), "未知商户")
                note = self.safe_get(row.get(note_col), "")
                raw_category = self.safe_get(row.get(category_col), "未分类")
                raw_account = self.safe_get(row.get(account_col), "微信")

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
                    source="wechat",
                    status="success"
                )

                # 验证交易
                self.validate_transaction(tx)
                transactions.append(tx)

            except Exception as e:
                self.logger.warning(f"第 {idx + 2} 行处理失败: {e}，已跳过")
                skipped_count += 1
                continue

        if skipped_count > 0:
            self.logger.info(f"跳过 {skipped_count} 条无效记录")

        return transactions


# 自动注册到全局注册表
from base_importer import registry
registry.register(WeChatImporter)
