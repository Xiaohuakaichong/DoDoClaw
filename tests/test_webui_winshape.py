"""Overlay window shape: window == card size, OS-rounded corners (Win32 calls mocked)."""

from __future__ import annotations

import ctypes
from types import SimpleNamespace

from dodoclaw.webui import app as webapp
from dodoclaw.webui import winshape


class FakeDwm:
    def __init__(self, hr=0):
        self.hr, self.calls = hr, []

    def DwmSetWindowAttribute(self, hwnd, attr, pv, size):
        self.calls.append((attr, ctypes.cast(pv, ctypes.POINTER(ctypes.c_uint)).contents.value))
        return self.hr


class FakeUser32:
    def __init__(self, w=320, h=300, dpi=144):
        self.w, self.h, self.dpi, self.rgn = w, h, dpi, None

    def GetWindowRect(self, hwnd, prect):
        r = prect._obj
        r.left, r.top, r.right, r.bottom = 24, 120, 24 + self.w, 120 + self.h
        return 1

    def GetDpiForWindow(self, hwnd):
        return self.dpi

    def SetWindowRgn(self, hwnd, rgn, redraw):
        self.rgn = rgn
        return 1


class FakeGdi:
    def __init__(self):
        self.args, self.deleted = None, []

    def CreateRoundRectRgn(self, *a):
        self.args = a
        return 777

    def DeleteObject(self, h):
        self.deleted.append(h)


def test_overlay_sizes_have_no_shadow_margin():
    assert (webapp.OV_W, webapp.OV_H) == (320, 300)  # .ov is 320px wide
    assert webapp.OV_COMPACT == (250, 40)  # .pill is 250x40
    assert webapp.OV_BG.startswith("#") and len(webapp.OV_BG) == 7


def test_noop_off_windows_or_without_hwnd():
    assert winshape.round_corners(None, build=22631) == ""
    assert winshape.round_corners(1234, build=0) == ""


def test_win11_uses_dwm_round_and_drops_system_border():
    dwm = FakeDwm()
    assert winshape.round_corners(1234, build=22631, user32=FakeUser32(), dwmapi=dwm, gdi32=FakeGdi()) == "dwm"
    assert dwm.calls[0] == (winshape.DWMWA_WINDOW_CORNER_PREFERENCE, winshape.DWMWCP_ROUND)
    assert dwm.calls[1] == (winshape.DWMWA_BORDER_COLOR, winshape.DWMWA_COLOR_NONE)


def test_win11_dwm_failure_falls_back_to_region():
    u, g = FakeUser32(), FakeGdi()
    assert winshape.round_corners(1234, build=22631, user32=u, dwmapi=FakeDwm(hr=-1), gdi32=g) == "region"
    assert u.rgn == 777


def test_win10_region_matches_window_and_dpi():
    u, g = FakeUser32(w=480, h=450, dpi=144), FakeGdi()
    assert winshape.round_corners(1234, build=19045, user32=u, dwmapi=FakeDwm(), gdi32=g) == "region"
    assert g.args == (0, 0, 481, 451, 24, 24)  # 2 * 8px radius * 1.5 scale
    assert g.deleted == []


def test_region_radius():
    assert winshape.region_radius(1.0) == 16
    assert winshape.region_radius(1.25) == 20
    assert winshape.region_radius(0) == 16


def test_hwnd_of():
    win = SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda: 4242)))
    assert winshape.hwnd_of(win) == 4242
    assert winshape.hwnd_of(SimpleNamespace(native=None)) is None
    assert winshape.hwnd_of(object()) is None


def _bridge_with_window(monkeypatch, shape="dwm"):
    b = webapp.Bridge.__new__(webapp.Bridge)
    calls = []
    b._ov_win = SimpleNamespace(
        resize=lambda w, h: calls.append(("resize", w, h)),
        move=lambda x, y: calls.append(("move", x, y)),
        show=lambda: calls.append(("show",)),
        hide=lambda: calls.append(("hide",)),
    )
    b._ov_shape = ""
    b._ov_shown = True
    b._ov_pending_size = b._ov_pending_pos = None
    b.overlay_forced = None
    b.compact = False
    monkeypatch.setattr(winshape, "hwnd_of", lambda w: 99)
    monkeypatch.setattr(winshape, "round_corners", lambda h: calls.append(("shape", h)) or shape)
    return b, calls


def test_compact_toggle_uses_card_sizes_and_shapes_once_with_dwm(monkeypatch):
    b, calls = _bridge_with_window(monkeypatch, "dwm")
    assert b.toggle_compact() is True
    assert b.toggle_compact() is False
    assert calls == [("resize", 250, 40), ("shape", 99), ("resize", 320, 300)]


def test_region_is_reapplied_after_every_fit(monkeypatch):
    b, calls = _bridge_with_window(monkeypatch, "region")
    b.fit_overlay(320, 286)
    b.fit_overlay(250, 40)
    b.fit_overlay(5000, 40)  # out of range: ignored
    assert calls == [("resize", 320, 286), ("shape", 99), ("resize", 250, 40), ("shape", 99)]


def test_overlay_page_has_no_outer_margin_or_shadow():
    html = (webapp.STATIC / "overlay.html").read_text(encoding="utf-8")
    assert "body{padding" not in html
    assert "html,body{background:#0a0c11" in html
    for line in html.splitlines():
        if line.startswith((".ov{", " box-shadow", ".ov.hot{", ".pill{", "@keyframes flash")):
            for part in line.split("box-shadow:")[1:]:
                for shadow in part.split(";")[0].split("}")[0].split("),"):
                    assert shadow.strip().startswith("inset"), line
    js = (webapp.STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "+ 24" not in js


def test_hidden_overlay_is_not_popped_up_by_resize_or_reset(monkeypatch):
    # pywebview's WinForms resize/move use SWP_SHOWWINDOW: never call them while hidden
    b, calls = _bridge_with_window(monkeypatch, "dwm")
    b._ov_shown = False
    b.fit_overlay(320, 106)
    b.toggle_compact()
    b.reset_overlay_pos()
    assert calls == []
    assert b.toggle_overlay() is True  # 小窗 chip: show, then apply parked pos + size
    assert calls == [("show",), ("move", *webapp.OV_POS), ("resize", 250, 40), ("shape", 99)]
    calls.clear()
    assert b.toggle_overlay() is False
    assert calls == [("hide",)]
    b.fit_overlay(320, 300)
    assert calls == [("hide",)] and b._ov_pending_size == (320, 300)


def test_overlay_min_size_allows_compact_pill():
    src = (webapp.Path(webapp.__file__)).read_text(encoding="utf-8")
    assert "min_size=(100, 40)" in src
    assert webapp.OV_COMPACT[0] >= 100 and webapp.OV_COMPACT[1] >= 40


def test_keep_on_top_uses_ctypes_setwindowpos_without_show():
    seen = []

    class U:
        def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
            seen.append((hwnd.value, after.value, flags))
            return 1

    assert winshape.keep_on_top(4242, user32=U()) is True
    hwnd, after, flags = seen[0]
    assert hwnd == 4242 and after == ctypes.c_void_p(-1).value
    assert flags & winshape.SWP_NOSIZE and flags & winshape.SWP_NOMOVE and flags & winshape.SWP_NOACTIVATE
    assert not flags & 0x0040  # SWP_SHOWWINDOW would pop a hidden overlay up
    assert winshape.keep_on_top(None, user32=U()) is False


def test_watch_never_uses_pywebview_on_top_setter():
    # window.on_top = True sets WinForms TopMost from a worker thread with the GIL
    # held -> deadlock with the UI thread's resize handler (overlay freeze).
    src = webapp.Path(webapp.__file__).read_text(encoding="utf-8")
    body = src.split("def _watch(self)")[1].split("def run_webui")[0]
    assert ".on_top" not in body and "_keep_overlay_on_top()" in body


def test_overlay_calls_are_serialized(monkeypatch):
    import threading
    import time

    b, calls = _bridge_with_window(monkeypatch, "region")
    active, overlap = [0], []

    def slow_resize(w, h):
        active[0] += 1
        if active[0] > 1:
            overlap.append((w, h))
        time.sleep(0.01)
        active[0] -= 1

    b._ov_win.resize = slow_resize
    monkeypatch.setattr(winshape, "keep_on_top", lambda h: slow_resize(0, 0))
    ts = [threading.Thread(target=f) for f in (b.toggle_compact, lambda: b.fit_overlay(320, 106),
                                                b._keep_overlay_on_top, b.toggle_compact) for _ in range(5)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert overlap == []


def test_no_overlay_opacity_control_d11():
    # The overlay window is opaque: a 透明度 slider would do nothing (PRD 6.6).
    html = (webapp.STATIC / "settings.html").read_text(encoding="utf-8")
    js = (webapp.STATIC / "settings.js").read_text(encoding="utf-8")
    ov = (webapp.STATIC / "overlay.js").read_text(encoding="utf-8")
    assert "不透明度" not in html and "透明度" not in html and 'id="sl-op"' not in html
    assert "overlay_opacity" not in js and "ov_opacity" not in ov


def test_inner_overlay_radii_are_smaller_than_the_window_corner():
    import re

    html = (webapp.STATIC / "overlay.html").read_text(encoding="utf-8")
    for sel in (".ib{", ".ans{", ".in .f{", ".in .mic{", ".alert{", ".soft{", ".in input{"):
        rule = html.split(sel, 1)[1].split("}", 1)[0]
        assert re.search(r"border-radius:6px", rule), sel
    assert winshape.RADIUS == 8
