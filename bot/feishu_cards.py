"""Pure functions returning Feishu interactive-card JSON.

All Decimals are formatted via `_fmt_money` / `_fmt_qty` so the returned dict is
JSON-serialisable. Card schema follows the Feishu v2 interactive card spec.
"""
from __future__ import annotations

import json
from decimal import Decimal

from config import settings
from bot.purchase_parser import ParseError
from bot.purchase_resolver import ResolvedPurchase, ResolveError, PendingLine


def _image_url(image: str | None) -> str | None:
    """Turn a stored part.image value into a public URL, or None.
    Already-absolute http(s) URLs pass through; a bare OSS key is prefixed with
    the public base. Returns None when there's no image or no base to build one."""
    if not image:
        return None
    if image.startswith("http://") or image.startswith("https://"):
        return image
    base = settings.oss_public_base_url
    return f"{base}/{image.lstrip('/')}" if base else None


def _fmt_money(d: Decimal) -> str:
    q = d.quantize(Decimal("0.01"))
    return format(q, "f")


def _fmt_qty(d: Decimal) -> str:
    return format(d.normalize(), "f") if d == d.to_integral_value() else format(d, "f")


def _md(text: str) -> dict:
    return {"tag": "div", "text": {"tag": "lark_md", "content": text}}


def _hr() -> dict:
    return {"tag": "hr"}


def _header(title: str, color: str = "blue") -> dict:
    return {
        "title": {"tag": "plain_text", "content": title},
        "template": color,
    }


def render_preview_card(data: ResolvedPurchase, token: str) -> dict:
    new_marker = " ⚠ 新店家" if data.vendor_is_new else ""
    elements: list[dict] = [
        _md(f"**店家：**{data.vendor_name}{new_marker}"),
        _hr(),
        _md("**明细：**"),
    ]
    for it in data.items:
        line = (
            f"`{it.part_id}` {it.part_name}\n"
            f"　 {_fmt_qty(it.qty)} × {it.unit} × {_fmt_money(it.price)} "
            f"= **{_fmt_money(it.amount)}**"
        )
        elements.append(_md(line))
    elements.append(_hr())
    elements.append(_md(
        f"**合计：{_fmt_money(data.total_amount)} 元 / 共 {len(data.items)} 项**"
    ))
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 确认建单"},
                "type": "primary",
                "value": {"action": "confirm", "token": token},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "❌ 取消"},
                "type": "default",
                "value": {"action": "cancel", "token": token},
            },
        ],
    })
    return {"header": _header("采购单预览", "blue"), "elements": elements}


def render_disambiguation_card(pending: PendingLine, token: str, done: int, total: int) -> dict:
    elements: list[dict] = [
        _md(
            f"**第 {pending.line_no} 行 “{pending.query}” 命中 {len(pending.candidates)} 个，选哪个？**"
        ),
        _md(
            f"（数量 {_fmt_qty(pending.qty)} × 单价 {_fmt_money(pending.price)}）　进度 {done + 1}/{total}"
        ),
    ]
    # One block per candidate: a description line (with a 查看图 link) followed by
    # its own select button, stacked vertically for clarity.
    for c in pending.candidates:
        spec_part = f"({c.spec})" if c.spec else ""
        url = _image_url(c.part_image)
        img_part = f" · [查看图]({url})" if url else " · 无图"
        elements.append(_md(f"`{c.part_id}` {c.part_name}{spec_part}{img_part}"))
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": f"选 {c.part_id}"},
                "type": "default",
                "value": {
                    "action": "disambiguate",
                    "token": token,
                    "line_no": pending.line_no,
                    "part_id": c.part_id,
                },
            }],
        })
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "❌ 取消"},
            "type": "default",
            "value": {"action": "cancel", "token": token},
        }],
    })
    return {"header": _header("需要确认", "orange"), "elements": elements}


def render_success_card(po_id: str, vendor: str, total: Decimal, item_count: int) -> dict:
    elements = [
        _md(f"**单号：**`{po_id}`"),
        _md(f"**店家：**{vendor}"),
        _md(f"**合计：**{_fmt_money(total)} 元 / {item_count} 项"),
    ]
    return {"header": _header("✅ 采购单已创建", "green"), "elements": elements}


def render_cancel_card() -> dict:
    return {
        "header": _header("已取消", "grey"),
        "elements": [_md("草稿已丢弃，未建单。")],
    }


def render_parse_error_card(errors: list[ParseError]) -> dict:
    lines = []
    for e in errors:
        if e.line_no == 0:
            lines.append(f"- {e.reason}")
        else:
            lines.append(f"- 第 {e.line_no} 行 `{e.raw_line}`：{e.reason}")
    return {
        "header": _header("❌ 解析失败", "red"),
        "elements": [_md("\n".join(lines))],
    }


def render_resolve_error_card(error: ResolveError) -> dict:
    if error.kind == "part_not_found":
        lines = [
            f"- 第 {row['line_no']} 行：`{row['part_id']}`"
            for row in error.detail["lines"]
        ]
        return {
            "header": _header("❌ 配件不存在", "red"),
            "elements": [_md("以下配件编号在系统中未找到：\n" + "\n".join(lines))],
        }
    if error.kind == "vendor_ambiguous":
        cands = "、".join(f"`{c}`" for c in error.detail["candidates"])
        return {
            "header": _header("❌ 店家名歧义", "red"),
            "elements": [_md(
                f"`{error.detail['input']}` 匹配到多个店家：{cands}\n请打更具体一些。"
            )],
        }
    return {
        "header": _header("❌ 校验失败", "red"),
        "elements": [_md(json.dumps(error.detail, ensure_ascii=False))],
    }


def render_token_expired_card() -> dict:
    return {
        "header": _header("⚠ 预览已失效", "orange"),
        "elements": [_md("草稿已过期（>1 小时），请重新发送消息。")],
    }


def render_already_created_card(po_id: str) -> dict:
    return {
        "header": _header("ℹ 这张单已建好", "blue"),
        "elements": [_md(f"单号：`{po_id}`")],
    }


def render_create_failed_card(message: str) -> dict:
    return {
        "header": _header("❌ 建单失败", "red"),
        "elements": [_md(message)],
    }


def render_system_error_card(message: str) -> dict:
    return {
        "header": _header("❌ 系统错误", "red"),
        "elements": [_md(message)],
    }
