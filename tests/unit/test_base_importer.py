"""
基础导入器单元测试

测试 base_importer.py 中的抽象基类
"""
import pytest
from pathlib import Path
from decimal import Decimal
from datetime import date

# 导入测试模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from base_importer import (
    Transaction,
    BaseImporter,
    ImportRegistry,
    ImportError,
    TransactionValidationError,
    FileFormatError,
    FileSizeError,
    MAX_FILE_SIZE,
    MIN_DATE,
    MAX_AMOUNT,
)


class TestTransaction:
    """测试交易记录类"""

    def test_create_transaction(self):
        """测试创建交易记录"""
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="美团外卖",
            amount=Decimal("35.50"),
            raw_category="餐饮",
            raw_account="支付宝",
            note="午餐",
            source="alipay",
            status="success"
        )
        
        assert tx.date == date(2026, 1, 15)
        assert tx.payee == "美团外卖"
        assert tx.amount == Decimal("35.50")
        assert tx.raw_category == "餐饮"
        assert tx.raw_account == "支付宝"
        assert tx.note == "午餐"
        assert tx.source == "alipay"
        assert tx.status == "success"

    def test_transaction_to_dict(self):
        """测试转换为字典"""
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="测试",
            amount=Decimal("10.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        d = tx.to_dict()
        
        assert isinstance(d, dict)
        assert d["date"] == date(2026, 1, 15)
        assert d["payee"] == "测试"
        assert d["amount"] == Decimal("10.00")

    def test_default_values(self):
        """测试默认值"""
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="测试",
            amount=Decimal("10.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        assert tx.note == ""
        assert tx.source == ""
        assert tx.status == "success"


class TestImportRegistry:
    """测试导入器注册表"""

    def test_register_importer(self):
        """测试注册导入器"""
        registry = ImportRegistry()
        
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        # 注册导入器
        result = registry.register(TestImporter)
        
        assert result == TestImporter
        assert len(registry._importers) == 1

    def test_register_invalid_importer(self):
        """测试注册无效导入器"""
        registry = ImportRegistry()
        
        with pytest.raises(ValueError, match="必须为BaseImporter的子类"):
            registry.register(str)  # 不是BaseImporter的子类

    def test_get_matching_importer(self):
        """测试获取匹配的导入器"""
        registry = ImportRegistry()
        
        class CSVImporter(BaseImporter):
            PLATFORM_NAME = "CSV"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return path.suffix.lower() == ".csv"
            
            def extract_transactions(self, path):
                return []
        
        class XLSXImporter(BaseImporter):
            PLATFORM_NAME = "XLSX"
            SUPPORTED_EXTENSIONS = [".xlsx"]
            
            def supports_file(self, path):
                return path.suffix.lower() == ".xlsx"
            
            def extract_transactions(self, path):
                return []
        
        registry.register(CSVImporter)
        registry.register(XLSXImporter)
        
        # 测试 CSV 文件
        csv_path = Path("test.csv")
        importer = registry.get_matching_importer(csv_path, {})
        assert importer.PLATFORM_NAME == "CSV"
        
        # 测试 XLSX 文件
        xlsx_path = Path("test.xlsx")
        importer = registry.get_matching_importer(xlsx_path, {})
        assert importer.PLATFORM_NAME == "XLSX"

    def test_get_matching_importer_not_found(self):
        """测试未找到匹配的导入器"""
        registry = ImportRegistry()
        
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        registry.register(TestImporter)
        
        with pytest.raises(FileFormatError):
            registry.get_matching_importer(Path("test.pdf"), {})

    def test_list_supported_formats(self):
        """测试列出支持的格式"""
        registry = ImportRegistry()
        
        class CSVImporter(BaseImporter):
            PLATFORM_NAME = "CSV"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        class XLSXImporter(BaseImporter):
            PLATFORM_NAME = "XLSX"
            SUPPORTED_EXTENSIONS = [".xlsx", ".xls"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        registry.register(CSVImporter)
        registry.register(XLSXImporter)
        
        formats = registry.list_supported_formats()
        
        assert ".csv" in formats
        assert ".xlsx" in formats
        assert ".xls" in formats


class TestBaseImporterValidation:
    """测试基类的验证方法"""

    def test_validate_transaction_success(self):
        """测试有效交易验证通过"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="测试",
            amount=Decimal("100.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        # 应该不抛出异常
        assert importer.validate_transaction(tx) is True

    def test_validate_transaction_missing_date(self):
        """测试缺少日期验证失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=None,  # 缺失
            payee="测试",
            amount=Decimal("100.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        with pytest.raises(TransactionValidationError):
            importer.validate_transaction(tx)

    def test_validate_transaction_negative_amount(self):
        """测试负数金额验证失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="测试",
            amount=Decimal("-100.00"),  # 负数
            raw_category="测试",
            raw_account="测试"
        )
        
        with pytest.raises(TransactionValidationError):
            importer.validate_transaction(tx)

    def test_validate_transaction_amount_too_large(self):
        """测试金额过大验证失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=date(2026, 1, 15),
            payee="测试",
            amount=Decimal("200000000"),  # 超过1亿
            raw_category="测试",
            raw_account="测试"
        )
        
        with pytest.raises(TransactionValidationError):
            importer.validate_transaction(tx)

    def test_validate_transaction_old_date(self):
        """测试日期过早验证失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=date(1999, 1, 1),  # 早于2000年
            payee="测试",
            amount=Decimal("100.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        with pytest.raises(TransactionValidationError):
            importer.validate_transaction(tx)

    def test_validate_transaction_future_date(self):
        """测试未来日期验证失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        tx = Transaction(
            date=date(2099, 1, 1),  # 未来日期
            payee="测试",
            amount=Decimal("100.00"),
            raw_category="测试",
            raw_account="测试"
        )
        
        with pytest.raises(TransactionValidationError):
            importer.validate_transaction(tx)


class TestBaseImporterParseMethods:
    """测试基类的解析方法"""

    def test_parse_amount_success(self):
        """测试金额解析成功"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        result = importer.parse_amount("¥1,234.56", 1)
        
        assert result == Decimal("1234.56")

    def test_parse_amount_invalid(self):
        """测试金额解析失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        with pytest.raises(TransactionValidationError):
            importer.parse_amount("invalid", 1)

    def test_parse_date_with_pandas(self):
        """测试日期解析（使用pandas）"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        result = importer.parse_date("2026-01-15", 1)
        
        assert result == date(2026, 1, 15)

    def test_parse_date_chinese_format(self):
        """测试中文日期格式解析"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        result = importer.parse_date("2026年1月15日", 1)
        
        assert result == date(2026, 1, 15)

    def test_parse_date_invalid(self):
        """测试日期解析失败"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        with pytest.raises(TransactionValidationError):
            importer.parse_date("invalid-date", 1)

    def test_safe_get_with_value(self):
        """测试安全获取（有值）"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        result = importer.safe_get("  测试值  ", "默认值")
        
        assert result == "测试值"

    def test_safe_get_with_none(self):
        """测试安全获取（None）"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        result = importer.safe_get(None, "默认值")
        
        assert result == "默认值"

    def test_escape_beancount_string(self):
        """测试Beancount字符串转义"""
        class TestImporter(BaseImporter):
            PLATFORM_NAME = "Test"
            SUPPORTED_EXTENSIONS = [".csv"]
            
            def supports_file(self, path):
                return False
            
            def extract_transactions(self, path):
                return []
        
        importer = TestImporter()
        
        # 测试引号转义
        result = importer.escape_beancount_string('商户"名称"')
        assert '""' in result  # 引号被转义
        
        # 测试换行符转义
        result = importer.escape_beancount_string("多行\n文本")
        assert "\n" not in result  # 换行被替换为空格


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
