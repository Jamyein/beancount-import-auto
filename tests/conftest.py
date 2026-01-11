"""
Pytest 共享配置

提供测试中常用的 fixtures 和配置
"""
import sys
import pytest
from pathlib import Path
from decimal import Decimal
from datetime import date
import tempfile
import os

# 确保 scripts 目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


@pytest.fixture
def sample_config_dict():
    """示例配置字典"""
    return {
        "openai": {
            "api_key": "test-key",
            "api_base": "https://api.deepseek.com",
            "model": "deepseek-chat"
        },
        "main_bean_file": "main.beancount",
        "monthly_dir": "data",
        "asset_mapping": {
            "Alipay": "Assets:Alipay:Cash",
            "wechat": "Assets:WeChat"
        },
        "my_accounts": [
            "Expenses:Food",
            "Expenses:Shopping",
            "Expenses:Transport",
            "Income:Salary"
        ]
    }


@pytest.fixture
def sample_transaction():
    """示例交易记录"""
    from base_importer import Transaction
    
    return Transaction(
        date=date(2026, 1, 15),
        payee="美团外卖",
        amount=Decimal("35.50"),
        raw_category="餐饮",
        raw_account="支付宝",
        note="午餐",
        source="alipay",
        status="success"
    )


@pytest.fixture
def temp_csv_file(tmp_path):
    """创建临时CSV文件"""
    content = """交易时间,交易号,交易对方,收/支,金额,来源,备注,标签
2026-01-15,2026011520004000,美团外卖,支出,35.50,支付宝余额,午餐,餐饮
2026-01-16,2026011620004000,滴滴出行,支出,28.00,支付宝余额,打车,交通
2026-01-17,2026011720004000,工资,收入,5000.00,银行卡,月薪,工资
"""
    file_path = tmp_path / "alipay_test.csv"
    file_path.write_text(content, encoding='gbk')
    return file_path


@pytest.fixture
def temp_excel_file(tmp_path):
    """创建临时Excel文件"""
    try:
        import pandas as pd
        
        data = {
            '交易时间': ['2026-01-15', '2026-01-16', '2026-01-17'],
            '交易对方': ['美团外卖', '滴滴出行', '工资'],
            '金额(元)': ['35.50', '28.00', '5000.00'],
            '支付方式': ['微信支付', '微信支付', '银行卡'],
            '当前状态': ['已完成', '已完成', '已完成']
        }
        df = pd.DataFrame(data)
        
        file_path = tmp_path / "wechat_test.xlsx"
        df.to_excel(file_path, index=False, engine='openpyxl')
        return file_path
    except ImportError:
        pytest.skip("openpyxl not installed")


@pytest.fixture
def mock_logger(mocker):
    """模拟日志器"""
    mock = mocker.patch('logger_config.get_logger')
    mock.return_value = mocker.MagicMock()
    return mock


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """自动清理环境"""
    # 确保不生成 pycache
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setattr(sys, "dont_write_bytecode", True)


def pytest_configure(config):
    """pytest 配置"""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """修改测试收集"""
    # 将集成测试放在最后
    items.sort(key=lambda item: (
        0 if "integration" not in item.keywords else 1,
        0 if "slow" not in item.keywords else 1,
        item.name
    ))
