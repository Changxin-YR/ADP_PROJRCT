"""ADP 智能体的身份摘要与行为契约资产。

智能体的两件事在这里集中定义，避免散落在路由与侧车适配器里：

* :func:`build_user_brief` / :func:`render_prompt`：把"当前登录者是谁、有哪些权限"
  注入模型上下文，让智能体的能力边界与登录者一致（权限校验仍在网关与业务接口）。
* :data:`AGENT_INSTRUCTIONS` / :func:`ensure_instructions`：harness 每个用户会话都会
  读取 ``$DSH_HOME/AGENTS.md``，因此把行为契约随代码一起安装，部署后立即生效。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

INSTRUCTION_FILE_NAME = "AGENTS.md"
_MAX_LISTED = 80

BEHAVIOUR_RULES = """【行为约定】
1. 你只能使用 adp_query（只读查询）、adp_mutation（准备写操作）、adp_ask_user（向用户提问）三个工具，不要臆造工具、接口或参数。
2. 查询一律走 adp_query；任何写入都先用 adp_mutation 准备，由用户在界面上点击确认后才会真正执行，你不得声称已经完成写入。
3. 只读数据可以分页：arguments 支持 page / page_size（单页上限 50）。需要更多数据时连续翻页，并在结果里说明"这是第 N 页，还有更多"。
4. 权限与登录者完全一致：只执行"当前登录用户"权限码覆盖的操作。权限不足时直接说明缺少哪项权限，不要反复重试、不要改用其它接口绕过。
5. 缺少必要信息时（例如缺塘口/批次/物料/数量/日期，或同一关键词命中多个对象，或口径不清），必须调用 adp_ask_user 提出一个具体问题，并给出 2-4 个可点击选项；禁止猜测参数。
6. 工具返回错误时，如实转述错误码与错误原文，禁止编造"服务未连接""域名配置问题""认证服务故障"等未经证实的原因，也不要建议联系管理员，除非错误信息本身这样说明。
7. 操作名（operation）必须取自工具说明里的清单；资源名（resource 等参数）拿不准时先用一次只读调用试探（例如主数据常用 ponds / ponds-groups / farms / areas / materials），遇到 RESOURCE_NOT_FOUND 就换一个名字或直接问用户，不要连续重试同一个错名。
8. 回答使用简体中文：先结论，再关键数据（列表/表格），必要时给下一步建议；数字必须与工具返回一致（不确定就不要报总数）；单轮最多 12 次工具调用，到上限先给已有结论并询问是否继续。
9. 需要用户补充信息时，必须直接调用 adp_ask_user；禁止只在文字里写"让我向用户提问""请提供…"却不调用工具——那样界面不会弹出输入框。同样禁止在文字里描述"我打算调用某个工具"。"""

AGENT_INSTRUCTIONS = """# ADP 塘小助 · 智能体行为契约

你是「潮汐养殖 · 鱼塘全流程管理平台」(ADP) 的业务助手，服务对象是当前登录用户。
你只能通过 adp_query / adp_mutation / adp_ask_user 三个工具工作，权限范围与登录者完全一致。

## 必须遵守
1. 查询用 adp_query；写入必须先 adp_mutation 准备，等用户点击「确认执行」后才算落地。
2. 只执行当前登录用户权限码覆盖的操作；权限不足时说明缺少哪项权限。
3. 信息不足或存在歧义时，调用 adp_ask_user 提问（带 2-4 个可点击选项），不要猜测。
4. 工具报错时如实转述错误码与原文，不得编造故障原因。
5. 回答用简体中文，先结论、后数据、必要时给下一步建议。
6. 需要补充信息就直接调用 adp_ask_user（不要用文字说"让我向用户提问"），不要在文字里预告工具调用。
7. 单轮最多调用 6 次工具；到达上限先给已有结论，再问用户是否继续。
8. 数字必须与工具返回一致；不确定就不要报总数。

## 常见任务（operation + arguments 起点，可按需加 page / page_size，单页 ≤50）
- 权限/身份：「查询我的权限」→ api.auth_me_get_api_v1_auth_me，{}。
- 主数据：塘口 → master_data.list_records，{resource: 'ponds'}；农场/片区/物料/业务伙伴同理换 resource。
- 生产记录：投喂 → production.list_records，{resource: 'feed-logs'}；用药 → 'medications'；日常操作/巡塘 → 'daily-operations'；出塘 → 'harvests'；批次 → 'batches'。
- 未巡检塘口：production.list_records，{resource: 'daily-operations', uninspected_on: 'today', page: 1, page_size: 20}。
- 仓储：库存/出入库/调拨/预警 → warehouse.list_records，{resource: 'issues'|'receipts'|'transfers'|'alerts'}。
- 采购/销售：purchase.list_orders、sales.list_orders。
- 成本费用：cost.list_entries。
- 待办/通知：workbench.list_work_items。
- 写入类（投喂、用药、出入库、采购、销售、成本）：先补齐字段，再 adp_mutation 准备，等待用户确认。
- 用户问「这个塘口 / 当前页面 / 它」时，优先用【当前页面】与【最近对话】里的信息消歧；仍不确定就 adp_ask_user。
"""


def _codes(values: Any) -> list[str]:
    """Flatten a list of role/scope rows or plain strings into stable codes."""
    codes: list[str] = []
    for item in values if isinstance(values, Iterable) and not isinstance(values, (str, bytes)) else []:
        if isinstance(item, dict):
            code = item.get("code") or item.get("scope_type") or item.get("name")
        else:
            code = item
        text = str(code).strip() if code is not None else ""
        if text and text not in codes:
            codes.append(text)
    return codes


def build_user_brief(user: dict[str, Any]) -> str:
    """Summarize the authenticated identity so the model never invents permissions."""
    if not isinstance(user, dict) or not user:
        return ""
    permissions = sorted(str(item) for item in (user.get("permissions") or []) if str(item).strip())
    listed = permissions[:_MAX_LISTED]
    lines = [
        "【当前登录用户】",
        f"姓名：{user.get('name') or user.get('login_name') or user.get('phone') or user.get('id')}",
        f"账号状态：{user.get('status') or 'unknown'}",
        f"角色：{'、'.join(_codes(user.get('roles'))) or '（无）'}",
        f"数据范围：{'、'.join(_codes(user.get('data_scopes'))) or '（无，按账号默认范围）'}",
        f"权限码（只能执行这些权限覆盖的操作）：{'、'.join(listed) or '（无）'}",
    ]
    if len(permissions) > len(listed):
        lines.append(f"（其余 {len(permissions) - len(listed)} 项权限已省略，仍以网关校验为准）")
    return "\n".join(lines)


MAX_HISTORY_TURNS = 8
MAX_HISTORY_CHARS = 2000


def turn_prompt_context(payload: dict[str, Any] | None) -> dict[str, str]:
    """Turn optional client context (current page, recent turns) into prompt text."""
    data = payload if isinstance(payload, dict) else {}
    page = str(data.get("context_path") or "").strip()[:200]
    lines: list[str] = []
    raw_history = data.get("history")
    if isinstance(raw_history, list):
        for item in raw_history[-MAX_HISTORY_TURNS:]:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip().replace("\n", " ")[:300]
            if not text:
                continue
            who = "用户" if str(item.get("role")) == "user" else "助手"
            lines.append(f"{who}：{text}")
    context: dict[str, str] = {}
    if page:
        context["page_context"] = page
    if lines:
        joined = "\n".join(lines)
        context["history_text"] = joined[-MAX_HISTORY_CHARS:]
    return context


def render_prompt(prompt: str, user_brief: str, page_context: str = "", history_text: str = "") -> str:
    """Attach identity, optional page/history context and the behaviour contract."""
    blocks: list[str] = []
    brief = (user_brief or "").strip()
    if brief:
        blocks.append(brief)
    if (page_context or "").strip():
        blocks.append(f"【当前页面】{page_context.strip()}")
    if (history_text or "").strip():
        blocks.append("【最近对话（由客户端携带，仅供参考）】\n" + history_text.strip())
    blocks.append(BEHAVIOUR_RULES)
    blocks.append(f"【用户请求】\n{prompt}")
    return "\n\n".join(blocks)


def ensure_instructions(dsh_home: str | Path) -> bool:
    """Install the behaviour contract into ``$DSH_HOME/AGENTS.md`` (best effort).

    The harness loads workspace instructions on every session baseline, so keeping
    the file in sync with the release is what actually changes model behaviour.
    A failed write must never break a conversation.
    """
    target = Path(dsh_home) / INSTRUCTION_FILE_NAME
    try:
        if target.is_file() and target.read_text(encoding="utf-8") == AGENT_INSTRUCTIONS:
            return True
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(AGENT_INSTRUCTIONS, encoding="utf-8")
    except OSError:
        return False
    return True
