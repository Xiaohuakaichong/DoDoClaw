"""Coach prompts.

The system prompt = a *style* part (who DoDoClaw is, how it talks — users may
override it via ``coach.system_style`` in settings.yaml) + fixed *rules* about
how to use the data we send. The rules are always appended, so a custom style
can't silently drop "don't invent cooldowns" or the BP instructions.
"""

from __future__ import annotations

DEFAULT_STYLE = """你是 DoDoClaw，一名简洁、实战向的 Dota 2 语音教练。
优先给出可执行建议（禁选、出装、站位、目标、时机），避免长篇理论。
用口语化中文；文字回答可稍完整（约 2–5 句），语音场景保持短。"""

CORE_RULES = """【作答规则】
- 结合【当前局势】、【目标计时】、（如有）BP/Meta 统计和知识库作答；信息不足时明确说明你的假设。
- 涉及技能/补丁数值以知识库为准，不要与补丁冲突地编造；不要编造对面的技能冷却，除非材料里有依据。
- 肉山/不朽盾/神龛/魔方时间只用【目标计时】里的数据；没有数据就直说看不到，别猜。GSI 看不到神符和肉山是否还在，不要说"现在有"。
- 储藏处里的物品还没带在身上；"回城卷轴: 没有"时可以顺带提醒补 TP。
- 【之前的对话】是本局里刚问过的问题，玩家追问（"那第二件呢""换成他呢"）时接着它答。
- BP 阶段：结合热门 ban/pick、对位克制与阵容短板，给出下一 ban/pick 建议，并用一句话说理由。"""

# Backward-compatible name: the full default system prompt.
DEFAULT_SYSTEM = f"{DEFAULT_STYLE}\n\n{CORE_RULES}\n"


def build_system_prompt(style: str | None = None) -> str:
    """Custom (or default) style + the fixed data-usage rules."""
    raw = style or ""
    style = raw.strip()
    if not style:
        return DEFAULT_SYSTEM
    if CORE_RULES in style:  # someone pasted the full default prompt
        return raw
    return f"{style}\n\n{CORE_RULES}\n"


def build_user_message(
    question: str,
    game_context: str,
    draft_context: str = "",
    knowledge_context: str = "",
    objectives_context: str = "",
    heroes_context: str = "",
) -> str:
    parts = [
        "【当前局势】\n",
        game_context,
        "\n\n",
    ]
    if objectives_context.strip():
        parts.extend(["【目标计时】\n", objectives_context.strip(), "\n\n"])
    if heroes_context.strip():
        parts.extend(["【问题里提到的英雄】\n", heroes_context.strip(), "\n\n"])
    if draft_context.strip():
        parts.extend(["【BP / Meta 参考】\n", draft_context.strip(), "\n\n"])
    if knowledge_context.strip():
        parts.extend([knowledge_context.strip(), "\n\n"])
    parts.extend(
        [
            "【玩家问题】\n",
            question.strip(),
            "\n\n请结合以上材料用中文回答；机制/补丁以知识库为准。",
        ]
    )
    return "".join(parts)
