# 代码重构说明

## 重构概览

本次重构对 beancount-import-auto 项目进行了系统性的架构升级，提升了代码质量、可维护性和扩展性。

## 重构内容

### ✅ 已完成的工作

#### 1. 核心架构优化

**新增文件：**
- `scripts/base_importer.py` - 导入器抽象基类
- `scripts/logger_config.py` - 统一日志系统
- `scripts/utils.py` - 公共工具函数
- `scripts/config_manager.py` - 配置管理器
- `scripts/ai_classifier.py` - AI 分类器（优化版）
- `scripts/importers/alipay_importer.py` - 支付宝导入器（重构版）
- `scripts/importers/wechat_importer.py` - 微信导入器（重构版）
- `scripts/importers/bank_importer.py` - 银行导入器（重构版）

**备份文件：**
- `scripts/importer_alipay.py.backup`
- `scripts/importer_wechat.py.backup`
- `scripts/memory_brain.py.backup`
- `scripts/importer_main.py.backup`

#### 2. 日志系统

**改进：**
- 从 `print` 输出升级到专业的 `logging` 模块
- 支持同时输出到文件和控制台
- 可配置的日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- 标准化的日志格式

**使用方式：**
```python
from logger_config import get_logger

logger = get_logger(__name__)
logger.info("信息消息")
logger.error("错误消息")
```

#### 3. 类型安全

**改进：**
- 所有新增模块添加完整的类型注解
- 使用 `typing` 模块提供类型提示
- 支持 IDE 的自动补全和静态检查

**示例：**
```python
def parse_csv(self, path: Path) -> List[Transaction]:
    """返回类型注解"""
    pass
```

#### 4. 错误处理

**改进：**
- 替换所有裸 `except` 为精准的异常捕获
- 新增自定义异常类（`ImportError`, `TransactionValidationError`, `FileFormatError`, `FileSizeError`）
- 分层的异常处理策略

**修复问题：**
- ❌ `except:` → ✅ `except FileNotFoundError:`
- ❌ `except Exception:` → ✅ `except (ValueError, KeyError):`

#### 5. 数据验证

**新增验证：**
- 文件大小限制（默认 10MB）
- 金额范围验证（必须为正数，小于1亿）
- 日期范围验证（2000年-今天）
- 必填字段检查

**示例：**
```python
# 验证金额
if tx.amount <= 0:
    raise TransactionValidationError(f"金额必须大于0: {tx.amount}")

# 验证日期
if tx.date < MIN_DATE:
    raise TransactionValidationError(f"日期过早: {tx.date}")
```

#### 6. 配置管理

**改进：**
- 配置集中化管理（`config_manager.py`）
- 配置验证（Schema）
- 支持平台特定配置

**新配置结构：**
```json
{
  "platforms": {
    "alipay": {
      "keywords": ["支付宝", "alipay"],
      "extensions": [".csv"],
      "field_mappings": {...}
    }
  }
}
```

#### 7. 导入器架构

**新设计：**
- 抽象基类 `BaseImporter`
- 导入器注册表 `ImportRegistry`
- 统一的 `Transaction` 数据结构

**新增导入器：**
- `AlipayImporter` - 继承 BaseImporter
- `WeChatImporter` - 继承 BaseImporter

**注册方式：**
```python
from base_importer import registry

@registry.register
class AlipayImporter(BaseImporter):
    pass
```

#### 8. AI 分类器优化

**改进：**
- 添加重试机制（使用 tenacity）
- 改进异常处理
- 优化缓存机制（原子性写入）
- 支持降级策略（SDK 不可用时使用 httpx）

**新增功能：**
- 自动重试（最多 3 次，指数退避）
- 速率限制检测和处理
- 缓存安全的原子性写入

#### 9. 公共工具函数

**新增工具：**
- `detect_file_by_keywords()` - 文件类型检测
- `find_header_line()` - 表头行查找
- `validate_success_status()` - 交易状态验证
- `clean_amount_string()` - 金额字符串清理
- `detect_asset_account()` - 资产账户识别
- `format_beancount_entry()` - Beancount 分录格式化

## 迁移指南

### 使用新的导入器

**旧方式：**
```python
from importer_alipay import is_alipay_file, parse_alipay
from importer_wechat import is_wechat_file, parse_wechat

if is_alipay_file(path):
    txs = parse_alipay(path)
```

**新方式：**
```python
from base_importer import registry
from config_manager import get_config

config = get_config()
importer = registry.get_matching_importer(path, config.to_dict())
transactions = importer.extract_transactions(path)
```

### 使用新的日志系统

**旧方式：**
```python
print(f"解析文件: {path}")
print(f"错误: {e}")
```

**新方式：**
```python
from logger_config import get_logger, setup_logging

setup_logging(level="INFO")
logger = get_logger(__name__)

logger.info(f"解析文件: {path}")
logger.error(f"错误: {e}")
```

### 配置更新

**新配置项：**
```json
{
  "platforms": {
    "alipay": {
      "keywords": ["支付宝", "alipay"],
      "extensions": [".csv"],
      "field_mappings": {
        "date": ["交易时间", "记录时间"],
        "amount": ["金额"],
        "payee": ["交易对方"]
      }
    }
  },
  "max_file_size": 10485760,
  "log_level": "INFO",
  "log_to_file": true,
  "log_to_console": true
}
```

## 测试新代码

### 测试支付宝导入器

```bash
python -c "
from scripts.importers.alipay_importer import AlipayImporter
from config_manager import get_config

config = get_config()
importer = AlipayImporter(config.to_dict())

# 测试文件识别
path = Path('bills/支付宝账单.csv')
print(f'支持: {importer.supports_file(path)}')

# 测试交易提取
if importer.supports_file(path):
    transactions = importer.extract_transactions(path)
    print(f'提取交易数: {len(transactions)}')
    if transactions:
        print(f'第一笔: {transactions[0].payee}')
"
```

### 测试日志系统

```bash
python -c "
from logger_config import setup_logging, get_logger

setup_logging(level='DEBUG')
logger = get_logger('test')

logger.debug('调试消息')
logger.info('信息消息')
logger.warning('警告消息')
logger.error('错误消息')
"
```

## 待完成工作

### 短期（1-2 周）

- [x] 重构银行导入器 `importer_bank.py`
- [ ] 添加单元测试框架
- [ ] 编写核心模块的单元测试
- [ ] 集成测试完整流程

### 中期（1-2 月）

- [ ] 性能基准测试
- [ ] 优化大文件处理
- [ ] 添加进度条显示
- [ ] 支持批量导入多个文件

### 长期（按需）

- [ ] Web 界面集成
- [ ] 支持更多银行格式
- [ ] CI/CD 流程搭建
- [ ] Docker 容器化

## 向后兼容性

为了确保平滑过渡，新代码保留了向后兼容性：

1. **MemoryBrain 类** - `ai_classifier.py` 中提供了兼容的 `MemoryBrain` 类
2. **降级逻辑** - 主流程中包含 `_fallback_main()` 以支持旧导入器
3. **配置格式** - 旧配置文件仍然有效，新配置项有默认值

## 已知问题

1. **银行导入器已重构** ✅ - `scripts/importers/bank_importer.py`
   - 支持 PDF 和 Excel 格式
   - 继承 BaseImporter 抽象基类
   - 包含完整的数据验证

2. **部分依赖缺失** - 重构代码依赖 `tenacity` 等新依赖
   - **解决方法**：运行 `pip install tenacity openpyxl`

## 建议后续步骤

1. **立即行动**
   - 安装新依赖：`pip install tenacity openpyxl`
   - 测试新导入器功能
   - 验证日志输出

2. **短期规划**
   - [x] 重构银行导入器
   - [ ] 添加测试覆盖
   - [ ] 更新文档

3. **长期规划**
   - 性能优化
   - 功能扩展
   - 用户界面改进

## 贡献者

- Sisyphus (AI Assistant) - 代码重构和优化

## 日期

- 重构日期：2026-01-11
- 分支：optimization/2024
