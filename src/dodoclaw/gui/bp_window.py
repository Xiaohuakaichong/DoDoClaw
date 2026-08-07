"""Dedicated BP / draft board window."""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from dodoclaw.meta.bp_board import BPBoard, HeroChip, build_bp_board
from dodoclaw.meta.draft import parse_draft_from_snapshot

if TYPE_CHECKING:
    from dodoclaw.service import DoDoClawService

logger = logging.getLogger(__name__)

BG = "#0b0c0f"
SURFACE = "#12141a"
SURFACE_2 = "#1a1d26"
BORDER = "#2a2e38"
TEXT = "#eceef2"
MUTED = "#8b929e"
ACCENT = "#c23c2a"
GREEN = "#2f9e6b"
GREEN_BG = "#14352a"
RED = "#d45c5c"
RED_BG = "#3a1c1c"
AMBER = "#d4a24c"
AMBER_BG = "#3a3018"
BLUE = "#5b8def"
BLUE_BG = "#1a2740"


def _tag_colors(tag: str) -> tuple[str, str]:
    if tag in {"recommend", "counter"}:
        return GREEN, GREEN_BG
    if tag in {"avoid"}:
        return RED, RED_BG
    if tag in {"ban_priority"}:
        return AMBER, AMBER_BG
    return MUTED, SURFACE_2


class HeroChipWidget(ctk.CTkFrame):
    def __init__(self, master, chip: HeroChip, **kwargs):
        fg, bg = _tag_colors(chip.tag)
        super().__init__(master, fg_color=bg, corner_radius=8, border_width=1, border_color=BORDER, **kwargs)
        title = chip.display
        if chip.win_rate is not None:
            title = f"{chip.display}  {chip.win_rate:.0%}"
        ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT,
            anchor="w",
        ).pack(fill="x", padx=8, pady=(6, 0))
        if chip.note:
            ctk.CTkLabel(
                self,
                text=chip.note,
                font=ctk.CTkFont(size=10),
                text_color=fg,
                anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 6))
        else:
            ctk.CTkLabel(self, text=" ", font=ctk.CTkFont(size=4)).pack()


class BPWindow(ctk.CTkToplevel):
    """
    Full BP board:
    - Top: draft slots (ally / enemy picks & bans)
    - Mid-left: ban priority + recommend / avoid
    - Mid-right: counters vs enemy
    - Bottom: lane recommendations
    """

    def __init__(
        self,
        master,
        service: DoDoClawService,
        *,
        on_ask_coach: Callable[[str], None] | None = None,
    ):
        super().__init__(master)
        self.title("DoDoClaw · BP 选人面板")
        self.geometry("1100x740")
        self.minsize(960, 640)
        self.configure(fg_color=BG)
        self.service = service
        self.on_ask_coach = on_ask_coach
        self._loading = False
        self._board: BPBoard | None = None

        self._build()
        self.after(80, self.refresh)
        # Keep on top briefly so user notices
        self.attributes("-topmost", True)
        self.after(400, lambda: self.attributes("-topmost", False))

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Toolbar
        bar = ctk.CTkFrame(self, fg_color=SURFACE, height=52, corner_radius=0)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar,
            text="BP 选人面板",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        self.status_lbl = ctk.CTkLabel(
            bar, text="加载中…", text_color=MUTED, font=ctk.CTkFont(size=12)
        )
        self.status_lbl.grid(row=0, column=1, sticky="w", padx=8)

        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.grid(row=0, column=2, padx=12, pady=10, sticky="e")

        ctk.CTkButton(
            actions,
            text="刷新数据",
            width=88,
            height=32,
            fg_color=ACCENT,
            hover_color="#a83426",
            command=self.refresh,
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            actions,
            text="问教练",
            width=72,
            height=32,
            fg_color=SURFACE_2,
            hover_color=BORDER,
            border_width=1,
            border_color=BORDER,
            command=self._ask_coach_bp,
        ).pack(side="left", padx=3)

        # Legend
        leg = ctk.CTkFrame(bar, fg_color="transparent")
        leg.grid(row=0, column=3, padx=(0, 16), sticky="e")
        for label, color in (
            ("推荐", GREEN),
            ("优先禁", AMBER),
            ("不推荐", RED),
            ("克制", BLUE),
        ):
            ctk.CTkLabel(
                leg, text=f"● {label}", text_color=color, font=ctk.CTkFont(size=11)
            ).pack(side="left", padx=4)

        # Scroll body
        self.body = ctk.CTkScrollableFrame(self, fg_color=BG)
        self.body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.body.grid_columnconfigure(0, weight=1)

        self._content = ctk.CTkFrame(self.body, fg_color=BG)
        self._content.pack(fill="both", expand=True, padx=14, pady=12)

    def refresh(self) -> None:
        if self._loading:
            return
        if not self.service or not getattr(self.service, "_draft_advisor", None):
            self.status_lbl.configure(
                text="Meta 未启用 · 请在设置里配置 OpenDota / STRATZ",
                text_color=RED,
            )
            return
        self._loading = True
        self.status_lbl.configure(text="正在拉取 Meta…", text_color=AMBER)

        def work() -> None:
            try:
                client = self.service._draft_advisor.client
                snap = self.service.snapshot()
                board = build_bp_board(client, snap, top_n=8)
                self.after(0, lambda: self._render(board))
            except Exception as exc:
                logger.exception("BP board failed")
                self.after(0, lambda: self._fail(str(exc)))
            finally:
                self._loading = False

        threading.Thread(target=work, name="bp-board", daemon=True).start()

    def _fail(self, err: str) -> None:
        self.status_lbl.configure(text=f"失败: {err}", text_color=RED)

    def _clear_content(self) -> None:
        for w in self._content.winfo_children():
            w.destroy()

    def _section(self, parent, title: str, subtitle: str = "") -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=12, border_width=1, border_color=BORDER)
        box.pack(fill="x", pady=(0, 12))
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            head,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=TEXT,
        ).pack(side="left")
        if subtitle:
            ctk.CTkLabel(
                head, text=subtitle, font=ctk.CTkFont(size=11), text_color=MUTED
            ).pack(side="left", padx=10)
        return box

    def _chip_row(self, parent, chips: list[HeroChip], empty: str = "暂无") -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        if not chips:
            ctk.CTkLabel(row, text=empty, text_color=MUTED, font=ctk.CTkFont(size=12)).pack(
                anchor="w", padx=4
            )
            return
        # wrap chips in grid
        grid = ctk.CTkFrame(row, fg_color="transparent")
        grid.pack(fill="x")
        cols = 4
        for i, chip in enumerate(chips):
            r, c = divmod(i, cols)
            cell = HeroChipWidget(grid, chip)
            cell.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            grid.grid_columnconfigure(c, weight=1)

    def _slot_strip(self, parent, title: str, chips: list[HeroChip], color: str) -> None:
        col = ctk.CTkFrame(parent, fg_color=SURFACE_2, corner_radius=10)
        col.pack(side="left", fill="both", expand=True, padx=4)
        ctk.CTkLabel(
            col,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=color,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        if not chips:
            ctk.CTkLabel(col, text="—", text_color=MUTED).pack(anchor="w", padx=10, pady=(0, 10))
            return
        for ch in chips:
            ctk.CTkLabel(
                col,
                text=f"• {ch.display}",
                text_color=TEXT,
                font=ctk.CTkFont(size=12),
                anchor="w",
            ).pack(fill="x", padx=10, pady=1)
        ctk.CTkLabel(col, text="", height=6).pack()

    def _render(self, board: BPBoard) -> None:
        self._board = board
        self._clear_content()

        phase = board.phase.replace("DOTA_GAMERULES_STATE_", "") if board.phase else "?"
        team = board.player_team or "未知"
        src = board.source or "?"
        self.status_lbl.configure(
            text=f"{src.upper()} · 阶段 {phase} · 我方 {team}"
            + (f" · {board.error}" if board.error else ""),
            text_color=RED if board.error else MUTED,
        )

        # 1) Live draft
        draft_box = self._section(
            self._content,
            "本局盘面",
            "来自 GSI draft · 无数据时可先点「刷新」或进入选人阶段",
        )
        slots = ctk.CTkFrame(draft_box, fg_color="transparent")
        slots.pack(fill="x", padx=8, pady=(0, 12))
        self._slot_strip(slots, "我方 Pick", board.ally_picks, GREEN)
        self._slot_strip(slots, "我方 Ban", board.ally_bans, AMBER)
        self._slot_strip(slots, "敌方 Pick", board.enemy_picks, RED)
        self._slot_strip(slots, "敌方 Ban", board.enemy_bans, MUTED)

        # 2) Two-column: ban/rec | counters
        mid = ctk.CTkFrame(self._content, fg_color="transparent")
        mid.pack(fill="x", pady=(0, 4))
        mid.grid_columnconfigure(0, weight=1)
        mid.grid_columnconfigure(1, weight=1)

        left = ctk.CTkFrame(mid, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        right = ctk.CTkFrame(mid, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ban_box = self._section(left, "优先禁", "高威胁 / 版本热门")
        self._chip_row(ban_box, board.ban_priority, "暂无禁人建议")

        rec_box = self._section(left, "推荐选择", "胜率偏高且样本足够 · 已过滤已选/已禁")
        self._chip_row(rec_box, board.pick_hot, "暂无推荐")

        avoid_box = self._section(left, "不推荐", "胜率偏低或高出场低胜")
        self._chip_row(avoid_box, board.avoid_pool, "暂无不推荐名单")

        # Counters
        ctr_box = self._section(
            right,
            "克制关系",
            "针对敌方已选 · 绿=可克 · 红=慎选",
        )
        if not board.counters:
            ctk.CTkLabel(
                ctr_box,
                text="敌方尚未选出英雄，或 GSI 未推送 draft。\n进入 BP 后点刷新即可看到对位克制。",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
                justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 14))
        else:
            for row in board.counters:
                block = ctk.CTkFrame(ctr_box, fg_color=SURFACE_2, corner_radius=10)
                block.pack(fill="x", padx=12, pady=(0, 10))
                ctk.CTkLabel(
                    block,
                    text=f"敌方 · {row.enemy_display}",
                    font=ctk.CTkFont(size=13, weight="bold"),
                    text_color=RED,
                ).pack(anchor="w", padx=10, pady=(8, 2))
                ctk.CTkLabel(
                    block, text="可克制对方（优先考虑）", text_color=GREEN, font=ctk.CTkFont(size=11)
                ).pack(anchor="w", padx=10)
                self._chip_row(block, row.counters, "样本不足")
                ctk.CTkLabel(
                    block, text="不建议对线/硬刚", text_color=RED, font=ctk.CTkFont(size=11)
                ).pack(anchor="w", padx=10)
                self._chip_row(block, row.weak_to, "—")

        # 3) Lanes
        lane_box = self._section(
            self._content,
            "分路建议",
            "STRATZ 有分路数据时更准；OpenDota 为角色近似",
        )
        lane_grid = ctk.CTkFrame(lane_box, fg_color="transparent")
        lane_grid.pack(fill="x", padx=8, pady=(0, 12))
        for i, lane in enumerate(board.lanes):
            card = ctk.CTkFrame(
                lane_grid, fg_color=SURFACE_2, corner_radius=10, border_width=1, border_color=BORDER
            )
            card.grid(row=0, column=i, sticky="nsew", padx=4)
            lane_grid.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(
                card,
                text=lane.label,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=BLUE,
            ).pack(anchor="w", padx=8, pady=(8, 4))
            ctk.CTkLabel(card, text="推荐", text_color=GREEN, font=ctk.CTkFont(size=10)).pack(
                anchor="w", padx=8
            )
            for ch in lane.recommend[:4]:
                wr = f" {ch.win_rate:.0%}" if ch.win_rate is not None else ""
                ctk.CTkLabel(
                    card, text=f"  {ch.display}{wr}", text_color=TEXT, font=ctk.CTkFont(size=11)
                ).pack(anchor="w", padx=6)
            ctk.CTkLabel(card, text="谨慎", text_color=RED, font=ctk.CTkFont(size=10)).pack(
                anchor="w", padx=8, pady=(6, 0)
            )
            for ch in lane.avoid[:3]:
                wr = f" {ch.win_rate:.0%}" if ch.win_rate is not None else ""
                ctk.CTkLabel(
                    card, text=f"  {ch.display}{wr}", text_color=MUTED, font=ctk.CTkFont(size=11)
                ).pack(anchor="w", padx=6)
            ctk.CTkLabel(card, text="", height=8).pack()

        if board.note:
            ctk.CTkLabel(
                self._content,
                text=board.note,
                text_color=MUTED,
                font=ctk.CTkFont(size=11),
                wraplength=1000,
                justify="left",
            ).pack(anchor="w", pady=(0, 8))

    def _ask_coach_bp(self) -> None:
        prompt = (
            "根据当前 BP 盘面和版本 meta，用简短中文告诉我："
            "下一步优先 ban 谁、我方该补什么位置、需要注意的克制。"
        )
        if self.on_ask_coach:
            self.on_ask_coach(prompt)
            self.status_lbl.configure(text="已发送给主窗口教练", text_color=GREEN)
        else:
            # fallback: show text advice in status via draft_advice
            def work() -> None:
                try:
                    text = self.service.draft_advice(speak=False)
                    self.after(
                        0,
                        lambda: (
                            self.status_lbl.configure(text="教练建议见下方刷新内容", text_color=GREEN),
                            self._append_coach_blob(text),
                        ),
                    )
                except Exception as exc:
                    self.after(
                        0,
                        lambda: self.status_lbl.configure(text=str(exc), text_color=RED),
                    )

            threading.Thread(target=work, daemon=True).start()

    def _append_coach_blob(self, text: str) -> None:
        box = self._section(self._content, "教练简报", "文本建议")
        ctk.CTkLabel(
            box,
            text=text[:2000],
            text_color=TEXT,
            font=ctk.CTkFont(size=12),
            justify="left",
            wraplength=1000,
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 14))
