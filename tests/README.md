# Beancount Import Auto - 单元测试框架

## 目录结构

```
tests/
├── __init__.py
├── conftest.py              # pytest 共享配置
├── fixtures/                # 测试数据
│   ├── alipay/             # 支付宝测试数据
│   ├── wechat/             # 微信测试数据
│   └── bank/               # 银行测试数据
├── unit/                    # 单元测试
│   ├── test_base_importer.py
│   ├── test_utils.py
│   ├── test_config_manager.py
│   └── test_ai_classifier.py
└── integration/             # 集成测试
    └── test_import_flow.py
```

## 快速开始

### 运行所有测试

```bash
pytest tests/
```

### 运行特定测试

```bash
# 运行单元测试
pytest tests/unit/

# 运行集成测试
pytest tests/integration/

# 运行特定文件
pytest tests/unit/test_utils.py

# 运行特定测试
pytest tests/unit/test_utils.py::test_clean_amount_string
```

### 生成测试覆盖率

```bash
pytest --cov=scripts --cov-report=html tests/
```

## 测试数据格式

### 支付宝 CSV 格式

```csv
交易时间,交易号,交易对方,收/支,金额,来源,备注,标签
2026-01-15,2026011520004000,美团外卖,支出,35.50,支付宝余额,午餐,餐饮
2026-01-16,2026011620004000,滴滴出行,支出,28.00,支付宝余额,打车,交通
```

### 微信 XLSX 格式

| 交易时间 | 交易类型 | 交易对方 | 金额(元) | 支付方式 | 当前状态 | 商品 |
|----------|----------|----------|----------|----------|----------|------|
| 2026-01-15 | 消费 | 美团外卖 | 35.50 | 微信支付 | 已完成 | 午餐 |
| 2026-01-16 | 消费 | 滴滴出行 | 28.00 | 微信支付 | 已完成 | 打车 |

## 常用 Fixtures

### `sample_config`
提供示例配置对象

### `sample_alipay_file`
创建临时支付宝账单文件

### `sample_wechat_file`
创建临时微信账单文件

### `sample_transactions`
提供示例交易列表

## CI/CD 配置

GitHub Actions 配置文件位于 `.github/workflows/tests.yml`

```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov
      - name: Run tests
        run: |
          pytest tests/ --cov=scripts
```
