"""Hang watchdog (all Win32 / faulthandler calls faked)."""

from __future__ import annotations

from dodoclaw.webui import hangwatch


def _watch(tmp_path, pings):
    log = []
    w = hangwatch.HangWatch(
        tmp_path / "logs" / "hang.log",
        get_hwnd=lambda: 77,
        ping=lambda h: pings.pop(0),
        arm=lambda t, repeat, file, exit: log.append(("arm", t, repeat, exit)),
        disarm=lambda: log.append(("disarm",)),
        sleep=lambda s: log.append(("sleep", s)),
    )
    return w, log


def test_responsive_ui_arms_then_disarms(tmp_path):
    w, log = _watch(tmp_path, [True])
    assert w.step() is True
    assert log == [("arm", hangwatch.DUMP_AFTER, False, False), ("disarm",)]
    assert (tmp_path / "logs" / "hang.log").exists()


def test_missed_ping_leaves_timer_armed_and_logs_once(tmp_path):
    w, log = _watch(tmp_path, [False, False, True])
    assert w.step() is False
    assert ("disarm",) not in log  # the C timer must still fire with the GIL stuck
    assert ("sleep", hangwatch.DUMP_AFTER + 1) in log
    w.step()
    assert w.step() is True
    w._file.close()
    text = (tmp_path / "logs" / "hang.log").read_text(encoding="utf-8")
    assert text.count("窗口线程没有响应") == 1 and "恢复响应" in text
    assert w.episodes == 1 and w.misses == 0


def test_no_window_yet_is_not_a_hang(tmp_path):
    w = hangwatch.HangWatch(tmp_path / "h.log", get_hwnd=lambda: None, ping=lambda h: False,
                            arm=lambda *a, **k: None, disarm=lambda: None, sleep=lambda s: None)
    assert w.step() is True


def test_ping_uses_sendmessagetimeout_abort_if_hung():
    seen = []

    class U:
        def SendMessageTimeoutW(self, hwnd, msg, wp, lp, flags, timeout, res):
            seen.append((msg, flags, timeout))
            return 1

    assert hangwatch.ping_hwnd(5, 1234, user32=U()) is True
    assert seen == [(0, 2, 1234)]


def test_release_app_starts_the_watchdog():
    from dodoclaw.webui import app as webapp

    src = webapp.Path(webapp.__file__).read_text(encoding="utf-8")
    started = src.split("def _started()")[1].split("webview.start")[0]
    assert "HangWatch(" in started and ".start()" in started