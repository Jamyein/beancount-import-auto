"""
支付宝账单导入器模块

重构版本：继承 BaseImporter，提供统一的接口和健壮的错误处理
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd

from base_importer import BaseImporter, Transaction, ImportRegistry
from utils import (
    ALIPAY_HEADER,
    ALIPAY_KEYWORDS,
    detect_file_by_keywords,
    find_header_line,
    normalize_dict_keys,
    validate_success_status,
)
from logger_config import get_logger

logger = get_logger(__name__)


class AlipayImporter(BaseImporter):
    """支付宝账单导入器

    支持格式：
        - CSV 格式（GBK 编码）
        - 文件名包含关键词自动识别

    表头格式：
        - 交易时间 / 记录时间
        - 交易对方
        - 收/支
        - 金额
        - 来源
        - 备注
        - 标签
    """

    PLATFORM_NAME = "Alipay"
    SUPPORTED_EXTENSIONS = ['.csv']
    ENCODING = 'gbk'

    def supports_file(self, path: Path) -> bool:
        """判断是否为支付宝账单

        Args:
            path: 文件路径

        Returns:
            是否支持该文件
        """
        # 扩展名校验
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
            return False

        # 文件名快速判断
        if detect_file_by_keywords(path, ALIPAY_KEYWORDS):
            self.logger.debug(f"通过文件名识别: {path.name}")
            return True

        # 内容兜底判断（检查表头）
        return self._validate_header(path)

    def _validate_header(self, path: Path) -> bool:
        """验证文件头是否包含支付宝标准表头

        Args:
            path: 文件路径

        Returns:
            是否为有效的支付宝账单
        """
        try:
            with open(path, 'r', encoding=self.ENCODING) as f:
                # 读取前20行查找表头
                lines = [f.readline() for _ in range(20)]

                # 检查是否包含关键表头字段
                required_cols = ['交易时间', '记录时间']
                for line in lines:
                    if any(col in line for col in required_cols):
                        # 进一步检查是否包含其他必需字段
                        if all(
                            h in line or any(h in other for other in lines)
                            for h in ALIPAY_HEADER[:6]  # 前6个是核心字段
                        ):
                            self.logger.debug(f"通过表头验证: {path.name}")
                            return True
                return False

        except (UnicodeDecodeError, IOError) as e:
            self.logger.debug(f"表头验证失败: {e}")
            return False
        except Exception as e:
            self.logger.warning(f"验证表头时发生异常: {e}")
            return False

    def extract_transactions(self, path: Path) -> List[Transaction]:
        """提取支付宝交易记录

        Args:
            path: CSV 文件路径

        Returns:
            交易记录列表

        Raises:
            FileFormatError: 文件格式不正确
            ImportError: 导入过程失败
        """
        try:
            # 验证文件大小
            self.validate_file_size(path)

            # 解析 CSV
            transactions = self._parse_csv(path)

            self.logger.info(f"成功解析 {len(transactions)} 条支付宝交易")
            return transactions

        except Exception as e:
            self.logger.error(f"解析支付宝账单失败: {path} - {e}")
            raise ImportError(f"支付宝账单解析失败: {e}") from e

    def _parse_csv(self, path: Path) -> List[Transaction]:
        """解析 CSV 文件

        Args:
            path: CSV 文件路径

        Returns:
            交易记录列表

        Raises:
            FileFormatError: 找不到有效表头
        """
        # 读取所有行
        try:
            with open(path, 'r', encoding=self.ENCODING) as f:
                lines = f.readlines()
        except UnicodeDecodeError as e:
            self.logger.error(f"文件编码错误（尝试 {self.ENCODING}）: {e}")
            raise FileFormatError(f"无法读取文件编码: {e}")

        # 查找表头行（支持 "交易时间" 或 "记录时间"）
        header_idx = -1
        for i, line in enumerate(lines):
            if "交易时间" in line or "记录时间" in line:
                header_idx = i
                break

        if header_idx < 0:
            raise FileFormatError("未找到有效的表头行（包含 '交易时间' 或 '记录时间'）")

        self.logger.debug(f"找到表头行: 第 {header_idx + 1} 行")

        # 解析 CSV 数据
        import csv
        import io

        csv_text = ''.join(lines[header_idx:])
        reader = csv.DictReader(io.StringIO(csv_text))

        transactions = []
        skipped_count = 0

        for line_num, row in enumerate(reader, start=header_idx + 2):
            try:
                # 标准化键名（去除空格，过滤空键）
                row = normalize_dict_keys(row)

                # 跳过无效行
                if not self._is_valid_record(row):
                    skipped_count += 1
                    continue

                # 创建交易对象
                tx = self._create_transaction(row, line_num)

                # 验证交易
                self.validate_transaction(tx)
                transactions.append(tx)

            except Exception as e:
                self.logger.warning(f"第 {line_num} 行处理失败: {e}，已跳过")
                skipped_count += 1
                continue

        if skipped_count > 0:
            self.logger.info(f"跳过 {skipped_count} 条无效记录")

        return transactions

    def _is_valid_record(self, row: Dict[str, str]) -> bool:
        """验证记录有效性

        Args:
            row: CSV 行数据

        Returns:
            是否为有效记录
        """
        # 检查金额是否存在
        amount = row.get("金额", "").strip()
        if not amount:
            return False

        # 检查交易状态（只有成功状态才处理）
        status = row.get("交易状态", "")
        if not validate_success_status(status):
            return False

        return True

    def _create_transaction(
        self,
        row: Dict[str, str],
        line_num: int
    ) -> Transaction:
        """创建标准化交易对象

        Args:
            row: CSV 行数据
            line_num: 行号（用于日志）

        Returns:
            标准化的 Transaction 对象
        """
        # 解析日期
        date_str = row.get("交易时间", row.get("记录时间", ""))
        date = self.parse_date(date_str, line_num)

        # 解析金额
        amount = self.parse_amount(row["金额"], line_num)

        # 判断方向
        direction = "out" if row.get("收/支") == "支出" else "in"

        # 提取字段（使用多层 fallback）
        payee = row.get("交易对方", "").strip()
        note = row.get("商品说明", "").strip() or row.get("备注", "").strip()
        raw_category = row.get("标签", "").strip() or row.get("交易分类", "").strip()
        raw_account = (
            row.get("来源", "").strip() or
            row.get("账户", "").strip() or
            row.get("收/付款方式", "").strip()
        )

        return Transaction(
            date=date,
            payee=payee or "未知商户",
            amount=amount,
            raw_category=raw_category or "未分类",
            raw_account=raw_account or "支付宝",
            note=note,
            source="alipay",
            status="success"
        )


# 自动注册到全局注册表
registry = ImportRegistry()
registry.register(AlipayImporter)
