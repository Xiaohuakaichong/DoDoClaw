DEFAULT_SYSTEM = """你是 DoDoClaw，一名简洁、实战向的 Dota 2 语音教练。
结合当前 GSI 局势与（如有）BP/Meta 统计作答；信息不足时明确说明假设。
优先给出可执行建议（禁选思路、出装、站位、目标、时机），避免长篇理论。
用口语化中文，适合语音播报，单次回答尽量短（约 1–3 句）。
不要编造精确的对面技能冷却，除非局势文本里有依据。
BP 阶段：结合热门 ban/pick、对位克制与阵容短板，给出下一 ban/pick 建议，并说明理由一句话。
"""


def build_user_message(
    question: str,
    game_context: str,
    draft_context: str = "",
) -> str:
    parts = [
        "【当前局势】\n",
        game_context,
        "\n\n",
    ]
    if draft_context.strip():
        parts.extend(["【BP / Meta 参考】\n", draft_context.strip(), "\n\n"])
    parts.extend(
        [
            "【玩家问题】\n",
            question.strip(),
            "\n\n请用适合语音播报的短中文回答。",
        ]
    )
    return "".join(parts)
