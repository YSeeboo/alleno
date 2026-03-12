"""
Tool definitions for the Allen Shop bot agent.
Uses OpenAI function-calling format (compatible with DeepSeek).
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "查询配件或饰品的当前库存数量",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "part 或 jewelry"},
                    "item_id": {"type": "string", "description": "物品 ID，如 PJ-0001 或 SP-0001"},
                },
                "required": ["item_type", "item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_log",
            "description": "查询配件或饰品的库存流水历史记录",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "part 或 jewelry"},
                    "item_id": {"type": "string", "description": "物品 ID，如 PJ-0001 或 SP-0001"},
                },
                "required": ["item_type", "item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_stock",
            "description": "入库：为指定配件或饰品增加库存",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "part 或 jewelry"},
                    "item_id": {"type": "string", "description": "物品 ID，如 PJ-0001"},
                    "qty": {"type": "number", "description": "入库数量（正数）"},
                    "reason": {"type": "string", "description": "入库原因，如 采购入库"},
                    "note": {"type": "string", "description": "备注（可选）"},
                },
                "required": ["item_type", "item_id", "qty", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deduct_stock",
            "description": "出库：从指定配件或饰品中扣减库存",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {"type": "string", "description": "part 或 jewelry"},
                    "item_id": {"type": "string", "description": "物品 ID，如 PJ-0001"},
                    "qty": {"type": "number", "description": "出库数量（正数）"},
                    "reason": {"type": "string", "description": "出库原因，如 销售出库"},
                    "note": {"type": "string", "description": "备注（可选）"},
                },
                "required": ["item_type", "item_id", "qty", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "获取订单基本信息，包括客户名、状态、总金额等",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单 ID，如 OR-0001"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_items",
            "description": "获取订单中的饰品清单（饰品ID、数量、单价等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单 ID，如 OR-0001"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_parts_summary",
            "description": "根据订单的饰品清单和 BOM，汇总生产所需的配件总用量",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单 ID，如 OR-0001"},
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_order_status",
            "description": "更新订单状态（待生产 / 生产中 / 已完成）",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单 ID，如 OR-0001"},
                    "status": {"type": "string", "description": "新状态：待生产、生产中 或 已完成"},
                },
                "required": ["order_id", "status"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plating_order",
            "description": "获取电镀单信息，包括供应商、状态及各明细项",
            "parameters": {
                "type": "object",
                "properties": {
                    "plating_order_id": {"type": "string", "description": "电镀单 ID，如 EP-0001"},
                },
                "required": ["plating_order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_plating_items",
            "description": "收回电镀配件：按明细项 ID 记录收回数量，更新库存",
            "parameters": {
                "type": "object",
                "properties": {
                    "plating_order_id": {"type": "string", "description": "电镀单 ID，如 EP-0001"},
                    "receipts": {
                        "type": "array",
                        "description": "收回明细列表，每项包含 plating_order_item_id 和 qty",
                        "items": {
                            "type": "object",
                            "properties": {
                                "plating_order_item_id": {"type": "integer", "description": "电镀明细行 ID"},
                                "qty": {"type": "number", "description": "本次收回数量"},
                            },
                            "required": ["plating_order_item_id", "qty"],
                        },
                    },
                },
                "required": ["plating_order_id", "receipts"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_handcraft_order",
            "description": "获取手工单信息，包括供应商、状态及配件/饰品明细",
            "parameters": {
                "type": "object",
                "properties": {
                    "handcraft_order_id": {"type": "string", "description": "手工单 ID，如 HC-0001"},
                },
                "required": ["handcraft_order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "receive_handcraft_jewelries",
            "description": "收回手工饰品：按饰品明细项 ID 记录收回数量，更新库存",
            "parameters": {
                "type": "object",
                "properties": {
                    "handcraft_order_id": {"type": "string", "description": "手工单 ID，如 HC-0001"},
                    "receipts": {
                        "type": "array",
                        "description": "收回明细列表，每项包含 handcraft_jewelry_item_id 和 qty",
                        "items": {
                            "type": "object",
                            "properties": {
                                "handcraft_jewelry_item_id": {"type": "integer", "description": "手工饰品明细行 ID"},
                                "qty": {"type": "number", "description": "本次收回数量"},
                            },
                            "required": ["handcraft_jewelry_item_id", "qty"],
                        },
                    },
                },
                "required": ["handcraft_order_id", "receipts"],
            },
        },
    },
]


def execute_tool(name: str, inputs: dict, db) -> str:
    """Dispatch a tool call by name, returning a human-readable result string."""
    try:
        if name == "get_stock":
            from services.inventory import get_stock
            qty = get_stock(db, inputs["item_type"], inputs["item_id"])
            return f"当前库存: {qty}"

        elif name == "get_stock_log":
            from services.inventory import get_stock_log
            logs = get_stock_log(db, inputs["item_type"], inputs["item_id"])
            if not logs:
                return "暂无库存记录"
            lines = [
                f"{l.created_at} {l.change_qty:+.0f} {l.reason}"
                + (f" ({l.note})" if l.note else "")
                for l in logs[:20]
            ]
            return "\n".join(lines)

        elif name == "add_stock":
            from services.inventory import add_stock
            add_stock(db, inputs["item_type"], inputs["item_id"],
                      float(inputs["qty"]), inputs["reason"], inputs.get("note"))
            db.commit()
            return f"入库成功：{inputs['item_type']} {inputs['item_id']} +{inputs['qty']}"

        elif name == "deduct_stock":
            from services.inventory import deduct_stock
            deduct_stock(db, inputs["item_type"], inputs["item_id"],
                         float(inputs["qty"]), inputs["reason"], inputs.get("note"))
            db.commit()
            return f"出库成功：{inputs['item_type']} {inputs['item_id']} -{inputs['qty']}"

        elif name == "get_order":
            from services.order import get_order
            order = get_order(db, inputs["order_id"])
            if order is None:
                return f"未找到订单: {inputs['order_id']}"
            return (
                f"订单 {order.id}\n"
                f"客户: {order.customer_name}\n"
                f"状态: {order.status}\n"
                f"总金额: {order.total_amount}"
            )

        elif name == "get_order_items":
            from services.order import get_order_items
            items = get_order_items(db, inputs["order_id"])
            if not items:
                return "该订单暂无明细"
            lines = [
                f"{item.jewelry_id} x{item.quantity} 单价:{item.unit_price}"
                + (f" 备注:{item.remarks}" if item.remarks else "")
                for item in items
            ]
            return "\n".join(lines)

        elif name == "get_parts_summary":
            from services.order import get_parts_summary
            summary = get_parts_summary(db, inputs["order_id"])
            if not summary:
                return "该订单无配件需求（BOM 为空或订单无明细）"
            lines = [f"{part_id}: {qty}" for part_id, qty in summary.items()]
            return "配件汇总:\n" + "\n".join(lines)

        elif name == "update_order_status":
            from services.order import update_order_status
            order = update_order_status(db, inputs["order_id"], inputs["status"])
            db.commit()
            return f"订单 {order.id} 状态已更新为: {order.status}"

        elif name == "get_plating_order":
            from services.plating import get_plating_order
            from models.plating_order import PlatingOrderItem
            order = get_plating_order(db, inputs["plating_order_id"])
            if order is None:
                return f"未找到电镀单: {inputs['plating_order_id']}"
            items = (
                db.query(PlatingOrderItem)
                .filter(PlatingOrderItem.plating_order_id == order.id)
                .all()
            )
            lines = [f"电镀单 {order.id} 供应商:{order.supplier_name} 状态:{order.status}"]
            for item in items:
                lines.append(
                    f"  明细#{item.id} {item.part_id} qty:{item.qty} "
                    f"已收:{item.received_qty} 状态:{item.status} "
                    f"电镀方式:{item.plating_method or '-'}"
                )
            return "\n".join(lines)

        elif name == "receive_plating_items":
            from services.plating import receive_plating_items
            updated = receive_plating_items(db, inputs["plating_order_id"], inputs["receipts"])
            db.commit()
            lines = [
                f"明细#{item.id} 已收:{item.received_qty}/{item.qty} 状态:{item.status}"
                for item in updated
            ]
            return "电镀收回成功:\n" + "\n".join(lines)

        elif name == "get_handcraft_order":
            from services.handcraft import get_handcraft_order
            from models.handcraft_order import HandcraftPartItem, HandcraftJewelryItem
            order = get_handcraft_order(db, inputs["handcraft_order_id"])
            if order is None:
                return f"未找到手工单: {inputs['handcraft_order_id']}"
            part_items = (
                db.query(HandcraftPartItem)
                .filter(HandcraftPartItem.handcraft_order_id == order.id)
                .all()
            )
            jewelry_items = (
                db.query(HandcraftJewelryItem)
                .filter(HandcraftJewelryItem.handcraft_order_id == order.id)
                .all()
            )
            lines = [f"手工单 {order.id} 供应商:{order.supplier_name} 状态:{order.status}"]
            lines.append("配件:")
            for p in part_items:
                lines.append(f"  {p.part_id} qty:{p.qty} bom参考:{p.bom_qty or '-'}")
            lines.append("饰品:")
            for j in jewelry_items:
                lines.append(
                    f"  明细#{j.id} {j.jewelry_id} qty:{j.qty} "
                    f"已收:{j.received_qty} 状态:{j.status}"
                )
            return "\n".join(lines)

        elif name == "receive_handcraft_jewelries":
            from services.handcraft import receive_handcraft_jewelries
            updated = receive_handcraft_jewelries(
                db, inputs["handcraft_order_id"], inputs["receipts"]
            )
            db.commit()
            lines = [
                f"明细#{ji.id} {ji.jewelry_id} 已收:{ji.received_qty}/{ji.qty} 状态:{ji.status}"
                for ji in updated
            ]
            return "手工收回成功:\n" + "\n".join(lines)

        else:
            return f"未知工具: {name}"

    except Exception as e:
        return f"错误: {e}"
