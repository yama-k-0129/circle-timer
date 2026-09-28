# -*- coding: utf-8 -*-
"""
Circle Timer - 常に前面に表示できる円形ビジュアルタイマー

操作:
  リング部分をドラッグ  : 時間セット(時計回り, 最大60分)
  マウスホイール        : ±1分 (Ctrl+ホイール: ±10秒)
  中央をクリック        : 開始 / 一時停止
  中央をドラッグ        : ウィンドウ移動
  ダブルクリック        : リセット
  右クリック            : メニュー(前面表示 / 透過度 / サイズ / 終了)
  Space / R             : 開始・停止 / リセット
"""
import sys
import time
import math

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QSettings, QSize, QLocale
from PySide6.QtGui import (QPainter, QPen, QColor, QBrush, QAction,
                           QRadialGradient, QPolygonF)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSlider,
                               QWidgetAction, QLabel, QHBoxLayout)

DIAL_MAX = 60 * 60          # ダイヤル1周 = 60分
TICK_MS = 200               # 動作中のみ更新
SNAP = 30                   # ドラッグセットのスナップ(秒)
STRINGS = {
    "ja": {
        "start": "開始", "pause": "一時停止", "reset": "リセット",
        "on_top": "常に前面に表示", "opacity": "透過度", "size": "サイズ",
        "small": "小", "medium": "中", "large": "大", "quit": "終了", "language": "言語",
    },
    "en": {
        "start": "Start", "pause": "Pause", "reset": "Reset",
        "on_top": "Always on top", "opacity": "Opacity", "size": "Size",
        "small": "Small", "medium": "Medium", "large": "Large", "quit": "Quit", "language": "Language",
    },
}
# Default language follows the system locale; the Language menu overrides it
DEFAULT_LANG = "ja" if QLocale.system().language() == QLocale.Language.Japanese else "en"


class CircleTimer(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("kouki", "CircleTimer")

        self.lang = self.settings.value("lang", DEFAULT_LANG)
        if self.lang not in STRINGS:
            self.lang = DEFAULT_LANG

        self.duration = int(self.settings.value("duration", 10 * 60))
        self.remaining = float(self.duration)
        self.running = False
        self.deadline = 0.0
        self.flash_on = False
        self.flash_count = 0

        self._drag_mode = None      # "move" | "set" | None
        self._press_pos = None
        self._moved = False

        self.tick_timer = QTimer(self)
        self.tick_timer.setInterval(TICK_MS)
        self.tick_timer.timeout.connect(self._tick)

        self.flash_timer = QTimer(self)
        self.flash_timer.setInterval(350)
        self.flash_timer.timeout.connect(self._flash)

        self.setWindowTitle("Circle Timer")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        size = int(self.settings.value("size", 260))
        self.resize(size, size)
        self.setMinimumSize(160, 160)

        self.set_on_top(self.settings.value("on_top", "true") == "true", init=True)
        self.setWindowOpacity(float(self.settings.value("opacity", 1.0)))

        pos = self.settings.value("pos")
        if pos:
            self.move(pos)

    # ---------- timer logic ----------
    def start(self):
        if self.remaining <= 0:
            self.remaining = float(self.duration)
        if self.remaining <= 0:
            return
        self.deadline = time.monotonic() + self.remaining
        self.running = True
        self.tick_timer.start()
        self.update()

    def pause(self):
        self.running = False
        self.tick_timer.stop()
        self.update()

    def toggle(self):
        self.pause() if self.running else self.start()

    def reset(self):
        self.pause()
        self.flash_timer.stop()
        self.flash_on = False
        self.remaining = float(self.duration)
        self.update()

    def _tick(self):
        self.remaining = self.deadline - time.monotonic()
        if self.remaining <= 0:
            self.remaining = 0.0
            self.pause()
            self._finish()
        self.update()

    def _finish(self):
        self.flash_count = 0
        self.flash_timer.start()
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            QApplication.beep()

    def _flash(self):
        self.flash_on = not self.flash_on
        self.flash_count += 1
        if self.flash_count >= 8:
            self.flash_timer.stop()
            self.flash_on = False
        self.update()

    # ---------- geometry helpers ----------
    def _center(self) -> QPointF:
        return QPointF(self.width() / 2, self.height() / 2)

    def _radius(self) -> float:
        return min(self.width(), self.height()) / 2 - 6

    def _ring_width(self) -> float:
        return self._radius() * 0.16

    def _on_ring(self, pos) -> bool:
        d = math.hypot(pos.x() - self._center().x(), pos.y() - self._center().y())
        r = self._radius()
        return r - self._ring_width() * 1.6 <= d <= r + 6

    def _handle_center(self):
        """先端ハンドルの中心座標と半径"""
        frac = min(max(self.remaining, 0) / DIAL_MAX, 1.0)
        c = self._center()
        r = self._radius()
        hr = r * 0.055
        a = math.radians(90 - frac * 360)
        return (QPointF(c.x() + (r - hr - r * 0.02) * math.cos(a),
                        c.y() - (r - hr - r * 0.02) * math.sin(a)), hr)

    def _on_handle(self, pos) -> bool:
        hc, hr = self._handle_center()
        return math.hypot(pos.x() - hc.x(), pos.y() - hc.y()) <= hr * 2.2

    def _angle_to_seconds(self, pos) -> int:
        dx = pos.x() - self._center().x()
        dy = pos.y() - self._center().y()
        ang = math.degrees(math.atan2(dx, -dy)) % 360   # 12時から時計回り
        sec = ang / 360 * DIAL_MAX
        sec = round(sec / SNAP) * SNAP
        return int(min(max(sec, 0), DIAL_MAX))

    # ---------- painting ----------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self._center()
        r = self._radius()

        # 背景の円(白い文字盤)
        bg = QRadialGradient(c, r)
        bg.setColorAt(0.0, QColor(253, 253, 254))
        bg.setColorAt(1.0, QColor(238, 240, 243))
        p.setPen(QPen(QColor(0, 0, 0, 50), 1.5))
        p.setBrush(QBrush(bg))
        p.drawEllipse(c, r, r)

        # 残り時間の扇形(12時から時計回り、中心まで塗る。反時計回りに減っていく)
        frac = min(max(self.remaining, 0) / DIAL_MAX, 1.0)
        pie_r = r - r * 0.12
        pie_rect = QRectF(c.x() - pie_r, c.y() - pie_r, pie_r * 2, pie_r * 2)
        if self.flash_on:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(229, 57, 53))
            p.drawEllipse(c, pie_r, pie_r)
        elif frac > 0:
            g = QRadialGradient(c, pie_r)
            g.setColorAt(0.0, QColor(244, 81, 76))
            g.setColorAt(1.0, QColor(198, 32, 28))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            if frac >= 0.9995:
                p.drawEllipse(c, pie_r, pie_r)
            else:
                p.drawPie(pie_rect, 90 * 16, int(-frac * 360 * 16))

        # 目盛り(5分ごと)
        p.setPen(QPen(QColor(0, 0, 0, 70), max(r * 0.012, 1.0), Qt.SolidLine, Qt.RoundCap))
        for i in range(12):
            a = math.radians(i * 30 - 90)
            x1 = c.x() + (r - r * 0.10) * math.cos(a)
            y1 = c.y() + (r - r * 0.10) * math.sin(a)
            x2 = c.x() + (r - r * 0.035) * math.cos(a)
            y2 = c.y() + (r - r * 0.035) * math.sin(a)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 先端ハンドル(ここをドラッグして時間をセット)
        hc, hr = self._handle_center()
        p.setPen(QPen(QColor(198, 32, 28), max(r * 0.016, 1.8)))
        p.setBrush(QColor(255, 255, 255))
        p.drawEllipse(hc, hr, hr)

        # 中央の再生/一時停止ボタン
        knob_r = r * 0.13
        p.setPen(QPen(QColor(0, 0, 0, 60), 1.2))
        p.setBrush(QColor(255, 255, 255, 248))
        p.drawEllipse(c, knob_r, knob_r)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(60, 64, 72))
        if self.running:
            bw = knob_r * 0.24
            bh = knob_r * 0.66
            gap = knob_r * 0.16
            p.drawRoundedRect(QRectF(c.x() - gap - bw, c.y() - bh / 2, bw, bh), bw / 3, bw / 3)
            p.drawRoundedRect(QRectF(c.x() + gap, c.y() - bh / 2, bw, bh), bw / 3, bw / 3)
        else:
            s = knob_r * 0.62
            tri = QPolygonF([QPointF(c.x() - s * 0.4, c.y() - s * 0.62),
                             QPointF(c.x() - s * 0.4, c.y() + s * 0.62),
                             QPointF(c.x() + s * 0.72, c.y())])
            p.drawPolygon(tri)

    # ---------- interaction ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        self._press_pos = e.globalPosition().toPoint()
        self._moved = False
        if self._on_handle(e.position()):
            self._drag_mode = "set"      # ハンドルは動作中でもドラッグ可
        elif self._on_ring(e.position()) and not self.running:
            self._drag_mode = "set"
            self._set_from_pos(e.position())
        else:
            self._drag_mode = "move"
            self._win_offset = self._press_pos - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_mode == "set":
            self._set_from_pos(e.position())
        elif self._drag_mode == "move":
            gp = e.globalPosition().toPoint()
            if (gp - self._press_pos).manhattanLength() > 4:
                self._moved = True
            self.move(gp - self._win_offset)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._drag_mode == "move" and not self._moved:
            self.toggle()
        self._drag_mode = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and not self._on_ring(e.position()):
            self.reset()

    def _set_from_pos(self, pos):
        self.flash_timer.stop()
        self.flash_on = False
        self.duration = self._angle_to_seconds(pos)
        self.remaining = float(self.duration)
        if self.running:
            self.deadline = time.monotonic() + self.remaining
        self.update()

    def wheelEvent(self, e):
        if self.running:
            return
        step = 10 if e.modifiers() & Qt.ControlModifier else 60
        delta = step if e.angleDelta().y() > 0 else -step
        self.duration = int(min(max(self.duration + delta, 0), DIAL_MAX))
        self.remaining = float(self.duration)
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            self.toggle()
        elif e.key() == Qt.Key_R:
            self.reset()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        T = STRINGS[self.lang]

        act_toggle = QAction(T["pause"] if self.running else T["start"], menu)
        act_toggle.triggered.connect(self.toggle)
        menu.addAction(act_toggle)

        act_reset = QAction(T["reset"], menu)
        act_reset.triggered.connect(self.reset)
        menu.addAction(act_reset)

        menu.addSeparator()

        act_top = QAction(T["on_top"], menu, checkable=True)
        act_top.setChecked(bool(self.windowFlags() & Qt.WindowStaysOnTopHint))
        act_top.toggled.connect(self.set_on_top)
        menu.addAction(act_top)

        # 透過度スライダー
        holder = QWidget(menu)
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.addWidget(QLabel(T["opacity"]))
        slider = QSlider(Qt.Horizontal, holder)
        slider.setRange(25, 100)
        slider.setValue(int(self.windowOpacity() * 100))
        slider.setFixedWidth(110)
        slider.valueChanged.connect(lambda v: self.setWindowOpacity(v / 100))
        lay.addWidget(slider)
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(holder)
        menu.addAction(wa)

        size_menu = menu.addMenu(T["size"])
        for key, px in (("small", 190), ("medium", 260), ("large", 340)):
            a = QAction(T[key], size_menu)
            a.triggered.connect(lambda _=False, s=px: self.resize(s, s))
            size_menu.addAction(a)

        lang_menu = menu.addMenu(T["language"])
        for code, label in (("en", "English"), ("ja", "日本語")):
            a = QAction(label, lang_menu, checkable=True)
            a.setChecked(self.lang == code)
            a.triggered.connect(lambda _=False, c=code: self.set_lang(c))
            lang_menu.addAction(a)

        menu.addSeparator()

        act_quit = QAction(T["quit"], menu)
        act_quit.triggered.connect(self.close)
        menu.addAction(act_quit)

        menu.exec(e.globalPos())

    def set_lang(self, code):
        self.lang = code
        self.settings.setValue("lang", code)

    def set_on_top(self, on: bool, init: bool = False):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if not init:
            self.show()

    def closeEvent(self, e):
        s = self.settings
        s.setValue("duration", self.duration)
        s.setValue("opacity", self.windowOpacity())
        s.setValue("on_top",
                   "true" if self.windowFlags() & Qt.WindowStaysOnTopHint else "false")
        s.setValue("size", self.width())
        s.setValue("pos", self.pos())
        e.accept()
        # Qt.Tool ウィンドウは lastWindowClosed を発火しないため明示的に終了する
        QApplication.quit()


def main():
    app = QApplication(sys.argv)
    w = CircleTimer()
    w.show()

    # 動作確認用: --shot <path> でスクリーンショットを保存して終了
    if "--shot" in sys.argv:
        out = sys.argv[sys.argv.index("--shot") + 1]
        w.duration = 25 * 60
        w.remaining = float(w.duration)

        def snap():
            w.grab().save(out)
            app.quit()
        QTimer.singleShot(400, snap)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
