# 电镀商家对账

## 入口与统计口径

- 电镀管理第四个 Tab：`/plating-reconciliation`，沿用 `plating` 权限。
- 默认全部商家、本月、全部付款状态；商家、回收创建日期、付款状态同时作用于顶部金额、商家汇总、明细和导出。
- 明细分页，汇总和导出不分页。回收时间取 `plating_receipt.created_at`，结束日期包含当天。
- 已付款是所选回收明细的已结算金额，不是按 `paid_at` 统计的付款流水。
- 待定价明细单独计数，不作为免费明细计入金额。

## 独立价格与付款生命周期

新表 `plating_reconciliation` 以回收明细 ID 为主键，保存可空改价、可空结算金额和结算时间。启动时随现有 `Base.metadata.create_all` 创建，无需修改原单的价格字段。

- 改价为空：沿用原明细金额；填写改价：实际回收数量 × 改价，按 Decimal 保留七位小数；0 是有效价格。
- 不回写原回收单价、金额、单据合计、配件成本或库存，也不影响同配件的其他回收记录或后续报价。
- 原回收单从未付款切换为已付款时，同一事务冻结该单全部明细的当前对账金额。
- 已付款不可改价；历史已付款没有快照时使用原明细金额。
- 原单撤回为未付款时清除快照，保留改价；再次付款重新冻结。
- 保留原系统对待定价回收单的付款能力，但冻结的未知金额仍标记“待定价”，不当作已付 0 元。
- 历史归档的明细可查看、统计和导出，不可对账改价。
- 原单删除 / 明细删除通过外键 `ON DELETE CASCADE` 清理独立记录。

改价、付款和原明细增删改使用相同回收单行锁，避免首次改价与付款竞争。锁定后重新读取数量、原价与改价，避免使用锁定前缓存的旧数据。服务只 flush，由现有 `get_db()` 统一 commit / rollback。

## API

- `GET /api/plating-reconciliation/`：筛选参数 `vendor_name`、`date_from`、`date_to`、`status`（未付款 / 已付款）；明细分页 `skip`、`limit`。
- `PATCH /api/plating-reconciliation/items/{id}`：`{"override_price": "0.45"}`；清空用 `null`。字段必须提供，非负，最多七位小数。
- `GET /api/plating-reconciliation/excel`：相同筛选参数，完整导出，不接受分页范围。

数值计算使用 Decimal，API 价格、金额用普通十进制字符串返回，避免科学计数法和浏览器浮点回写。

## Excel

1. **回收明细**（第一个且默认打开）：回收时间、配件、电镀方式、回收数量、单位、重量、单价、改价、金额、备注。
2. **商家汇总**：商家名称、应付款、已付款、待付款、待定价明细数，以及合计。

回收单号、商家名称、配件编号、电镀单号、付款状态仅在页面明细保留，不进入明细导出。文本强制作为字符串写入，避免用户备注被当作 Excel 公式执行。

- 改价列的数据使用红色字体，表头保持原样。
- 数量、单价、改价及金额保持数值类型；整数不显示末尾小数点，小数只显示有效位数。
- 重量与页面明细一致，保留原单位，不补多余的小数位；未填写重量时保持为空。

## 验证

仅在新建、可丢弃的 PostgreSQL 测试库执行后端测试。测试夹具会清空表并在结束时删除表，**禁止使用业务库或预览库**。

```sh
TEST_DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/NEW_ISOLATED_test .venv/bin/pytest -q tests/test_plating_reconciliation.py tests/test_api_plating_receipt.py
```

前端在 `frontend/` 执行：

```sh
node --test tests/*.test.mjs
npm run build
```

本功能不增加独立付款状态系统、部分付款、付款流水或自动损耗扣款抵扣。
