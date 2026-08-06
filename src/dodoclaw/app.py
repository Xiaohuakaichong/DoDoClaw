from __future__ import annotations

"""CLI interactive shell — thin wrapper around DoDoClawService."""

from rich.console import Console
from rich.panel import Panel

from dodoclaw.service import DoDoClawService

console = Console()


class DoDoClawApp:
    def __init__(self) -> None:
        self.service = DoDoClawService(
            on_log=self._on_log,
            on_reminder=self._on_reminder,
        )

    def _on_log(self, level: str, msg: str) -> None:
        style = {
            "info": "green",
            "warning": "yellow",
            "error": "red",
            "debug": "dim",
        }.get(level.lower(), "white")
        console.print(f"[{style}]{msg}[/{style}]")

    def _on_reminder(self, event) -> None:
        console.print(Panel(event.message, title="⏰ 提醒", border_style="yellow"))

    def handle_question(self, text: str) -> str:
        answer = self.service.ask(text, speak=True)
        if answer:
            console.print(Panel(answer, title="🦀 DoDoClaw", border_style="magenta"))
        return answer

    def run_interactive(self) -> None:
        self.service.start()
        console.print(
            Panel.fit(
                "[bold]DoDoClaw[/bold] CLI 模式\n"
                f"GSI: http://{self.service.gsi.host}:{self.service.gsi.port}/\n"
                "命令: 直接输入问题 | /status | /listen | /quit\n"
                "桌面版: python -m dodoclaw gui",
                border_style="green",
            )
        )
        try:
            while self.service.running:
                try:
                    line = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n退出中…")
                    break

                if not line:
                    continue
                if line in {"/q", "/quit", "/exit", "quit", "exit"}:
                    break
                if line == "/status":
                    console.print(self.service.status_text())
                    continue
                if line == "/listen":
                    text = self.service.listen_once()
                    if text:
                        self.handle_question(text)
                    else:
                        console.print("[dim]未识别到内容[/dim]")
                    continue
                self.handle_question(line)
        finally:
            self.service.stop()
