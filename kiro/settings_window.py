# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Single-panel settings window for Kiro Gateway."""

from typing import Callable, Dict, List, Optional, Tuple

import os

import objc
from AppKit import (
    NSApplication,
    NSMakeRect,
    NSView,
    NSWindow,
    NSTextField,
    NSSecureTextField,
    NSButton,
    NSScrollView,
    NSApplicationActivationPolicyAccessory,
    NSApp,
    NSBezelStyleRegularSquare,
    NSImage,
    NSButtonTypeSwitch,
    NSColor,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
)
from Foundation import NSMakePoint, NSMakeSize

_SECRET_KEYS = {"PROXY_API_KEY"}
_HTTPS_KEYS = {"SSL_CERTFILE", "SSL_KEYFILE"}

_ADVANCED_KEYS = {
    "KIRO_CREDS_FILE", "KIRO_CLI_DB_FILE", "KIRO_API_REGION",
    "VPN_PROXY_URL", "DEBUG_MODE", "SSL_CERTFILE", "SSL_KEYFILE",
}

_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources")

_W = 560.0
_PAD = 14.0
_ROW_H = 28.0
_ROW_GAP = 6.0
_LABEL_W = 160.0
_FIELD_W = 352.0
_BTN_AREA = 44.0
_MAX_VIS_H = 520.0


def _load_icon(name: str) -> Optional[NSImage]:
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        name.replace("-", "."), None
    )
    if img:
        return img
    path = os.path.join(_ICON_DIR, f"{name}.png")
    if os.path.exists(path):
        return NSImage.alloc().initWithContentsOfFile_(path)
    return None


class _FlippedView(NSView):

    def isFlipped(self) -> bool:  # noqa: N802
        return True


class SettingsWindowController:

    def __init__(
        self,
        keys: List[str],
        labels: Dict[str, str],
        values: Dict[str, str],
        on_save: Callable[[Dict[str, str]], None],
    ):
        self.keys = keys
        self.labels = labels
        self.initial_values = dict(values)
        self.on_save = on_save
        self.fields: Dict[str, NSTextField] = {}
        self._secret_pairs: Dict[str, Tuple[NSSecureTextField, NSTextField]] = {}
        self._secret_rows: Dict[str, NSView] = {}

        self._advanced_visible: bool = False
        self._advanced_views: List[NSView] = []
        self._https_checkbox: Optional[NSButton] = None
        self._advanced_toggle_btn: Optional[NSButton] = None
        self._scroll_view: Optional[NSScrollView] = None

        self._collapsed_h: float = 0.0
        self._expanded_h: float = 0.0
        self._canvas_w: float = 0.0

        self.window: Optional[NSWindow] = None

    def show(self) -> None:
        app = NSApplication.sharedApplication()
        if app.activationPolicy() != NSApplicationActivationPolicyAccessory:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        window = self._build_window()
        self.window = window
        window.center()
        window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _row_stride(self) -> float:
        return _ROW_H + _ROW_GAP

    def _build_window(self) -> NSWindow:
        regular_keys = [k for k in self.keys if k not in _ADVANCED_KEYS]
        adv_non_tls = [k for k in self.keys if k in _ADVANCED_KEYS and k not in _HTTPS_KEYS]
        tls_keys = [k for k in ("SSL_CERTFILE", "SSL_KEYFILE") if k in self.keys]

        https_enabled = bool(
            self.initial_values.get("SSL_CERTFILE", "").strip()
            or self.initial_values.get("SSL_KEYFILE", "").strip()
        )

        stride = self._row_stride()
        n_regular = len(regular_keys)
        n_adv_content = len(adv_non_tls) + 1 + len(tls_keys)

        # Canvas height when expanded (all rows visible)
        # Layout top-to-bottom: gap, row, gap, row, ..., gap at bottom
        collapsed_h = _ROW_GAP + (n_regular + 1) * stride   # +1 for toggle btn
        expanded_h = collapsed_h + n_adv_content * stride

        canvas_w = _W - _PAD * 2
        self._collapsed_h = collapsed_h
        self._expanded_h = expanded_h
        self._canvas_w = canvas_w

        canvas = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, 0, canvas_w, expanded_h))

        y = _ROW_GAP

        for key in regular_keys:
            self._place_row(key, canvas, y, canvas_w)
            y += stride

        # Advanced toggle button row
        adv_btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, y, 140, _ROW_H))
        adv_btn.setTitle_("▶  Advanced")
        adv_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        adv_btn.setBordered_(False)
        adv_btn.setAlignment_(0)
        adv_btn.setTarget_(self)
        adv_btn.setAction_("toggleAdvanced:")
        self._advanced_toggle_btn = adv_btn
        canvas.addSubview_(adv_btn)
        y += stride

        adv_views: List[NSView] = []

        for key in adv_non_tls:
            row = self._place_row(key, canvas, y, canvas_w)
            adv_views.append(row)
            y += stride

        cb = NSButton.alloc().initWithFrame_(NSMakeRect(0, y, canvas_w, _ROW_H))
        cb.setButtonType_(NSButtonTypeSwitch)
        cb.setTitle_("  Enable HTTPS (TLS)")
        cb.setState_(1 if https_enabled else 0)
        cb.setTarget_(self)
        cb.setAction_("httpsToggled:")
        self._https_checkbox = cb
        canvas.addSubview_(cb)
        adv_views.append(cb)
        y += stride

        for key in tls_keys:
            row = self._place_row(key, canvas, y, canvas_w)
            adv_views.append(row)
            field = self.fields.get(key)
            if field is not None:
                field.setEnabled_(https_enabled)
                field.setTextColor_(
                    NSColor.controlTextColor() if https_enabled
                    else NSColor.disabledControlTextColor()
                )
            y += stride

        self._advanced_views = adv_views
        for v in adv_views:
            v.setHidden_(True)

        viewport_h = min(collapsed_h, _MAX_VIS_H)
        sv = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(_PAD, _BTN_AREA, canvas_w, viewport_h)
        )
        sv.setDocumentView_(canvas)
        sv.setHasVerticalScroller_(True)
        sv.setHasHorizontalScroller_(False)
        sv.setAutohidesScrollers_(True)
        sv.setBorderType_(0)
        sv.setDrawsBackground_(False)
        sv.setBackgroundColor_(NSColor.windowBackgroundColor())
        self._scroll_view = sv

        canvas.scrollPoint_(NSMakePoint(0, 0))

        win_h = viewport_h + _BTN_AREA + 4
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, _W, win_h),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
            2,
            False,
        )
        window.setTitle_("Kiro Gateway — Settings")
        window.setReleasedWhenClosed_(False)

        cv = window.contentView()
        cv.addSubview_(sv)

        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(_W - 174, 8, 80, _BTN_H := 28))
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(1)
        save_btn.setTarget_(self)
        save_btn.setAction_("saveClicked:")
        cv.addSubview_(save_btn)

        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(_W - 86, 8, 80, 28))
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(1)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelClicked:")
        cv.addSubview_(cancel_btn)

        return window

    def _place_row(self, key: str, parent: NSView, y: float, canvas_w: float) -> NSView:
        row = _FlippedView.alloc().initWithFrame_(NSMakeRect(0, y, canvas_w, _ROW_H))

        lbl = NSTextField.labelWithString_(self.labels.get(key, key))
        lbl.setFrame_(NSMakeRect(0, 0, _LABEL_W, _ROW_H))
        lbl.setAlignment_(0)
        row.addSubview_(lbl)

        if key in _SECRET_KEYS:
            secure, plain, btn = self._make_secret_field(key)
            f_w = _FIELD_W - 36
            secure.setFrame_(NSMakeRect(_LABEL_W + 4, 0, f_w, _ROW_H))
            btn.setFrame_(NSMakeRect(_LABEL_W + 4 + f_w + 4, 0, 28, _ROW_H))
            row.addSubview_(secure)
            row.addSubview_(btn)
            self._secret_pairs[key] = (secure, plain)
            self._secret_rows[key] = row
            self.fields[key] = secure
        else:
            field = NSTextField.alloc().initWithFrame_(
                NSMakeRect(_LABEL_W + 4, 0, _FIELD_W, _ROW_H)
            )
            field.setStringValue_(self.initial_values.get(key, ""))
            field.setPlaceholderString_(f"{self.labels.get(key, key)} — empty clears the entry")
            field.cell().setWraps_(False)
            field.cell().setScrollable_(True)
            row.addSubview_(field)
            self.fields[key] = field

        parent.addSubview_(row)
        return row

    def _make_secret_field(self, key: str) -> Tuple[NSSecureTextField, NSTextField, NSButton]:
        initial = self.initial_values.get(key, "")
        placeholder = f"{self.labels.get(key, key)} — empty clears the entry"
        f_w = _FIELD_W - 36

        secure = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, f_w, _ROW_H))
        secure.setStringValue_(initial)
        secure.setPlaceholderString_(placeholder)

        plain = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, f_w, _ROW_H))
        plain.setStringValue_(initial)
        plain.setPlaceholderString_(placeholder)
        plain.cell().setWraps_(False)
        plain.cell().setScrollable_(True)

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 28, _ROW_H))
        btn.setBezelStyle_(NSBezelStyleRegularSquare)
        btn.setBordered_(False)
        eye_img = _load_icon("eye")
        if eye_img:
            btn.setImage_(eye_img)
        btn.setToolTip_("Show / hide")
        btn.setTarget_(self)
        objc.setAssociatedObject(btn, b"secret_key", key, objc.OBJC_ASSOCIATION_RETAIN)
        btn.setAction_("toggleReveal:")

        return secure, plain, btn

    def toggleAdvanced_(self, sender) -> None:  # noqa: N802
        self._advanced_visible = not self._advanced_visible
        hidden = not self._advanced_visible
        for v in self._advanced_views:
            v.setHidden_(hidden)

        arrow = "▼" if self._advanced_visible else "▶"
        if self._advanced_toggle_btn is not None:
            self._advanced_toggle_btn.setTitle_(f"{arrow}  Advanced")

        if self._scroll_view is not None:
            new_canvas_h = self._expanded_h if self._advanced_visible else self._collapsed_h
            viewport_h = min(new_canvas_h, _MAX_VIS_H)
            self._scroll_view.setFrame_(
                NSMakeRect(_PAD, _BTN_AREA, self._canvas_w, viewport_h)
            )
            if self.window is not None:
                new_content_h = viewport_h + _BTN_AREA + 4
                self.window.setContentSize_(NSMakeSize(_W, new_content_h))
            if self._advanced_visible:
                doc = self._scroll_view.documentView()
                doc.scrollPoint_(NSMakePoint(0, 0))

    def httpsToggled_(self, sender) -> None:  # noqa: N802
        enabled = sender.state() == 1
        for key in ("SSL_CERTFILE", "SSL_KEYFILE"):
            field = self.fields.get(key)
            if field is None:
                continue
            field.setEnabled_(enabled)
            field.setTextColor_(
                NSColor.controlTextColor() if enabled
                else NSColor.disabledControlTextColor()
            )

    def toggleReveal_(self, sender) -> None:  # noqa: N802
        key = objc.getAssociatedObject(sender, b"secret_key")
        if key is None or key not in self._secret_pairs:
            return

        secure, plain = self._secret_pairs[key]
        row = self._secret_rows[key]
        currently_secure = self.fields[key] is secure

        if currently_secure:
            plain.setStringValue_(secure.stringValue())
        else:
            secure.setStringValue_(plain.stringValue())

        (secure if currently_secure else plain).removeFromSuperview()
        next_field = plain if currently_secure else secure
        f_w = _FIELD_W - 36
        next_field.setFrame_(NSMakeRect(_LABEL_W + 4, 0, f_w, _ROW_H))
        row.addSubview_(next_field)
        row.addSubview_(sender)
        self.fields[key] = next_field

        new_icon = _load_icon("eye-slash" if currently_secure else "eye")
        if new_icon:
            sender.setImage_(new_icon)

    def saveClicked_(self, sender) -> None:  # noqa: N802
        collected = {key: field.stringValue() for key, field in self.fields.items()}
        if self._https_checkbox is not None and self._https_checkbox.state() == 0:
            for key in _HTTPS_KEYS:
                if key in collected:
                    collected[key] = ""
        self._close()
        self.on_save(collected)

    def cancelClicked_(self, sender) -> None:  # noqa: N802
        self._close()

    def windowWillClose_(self, notification) -> None:  # noqa: N802
        self.window = None

    def _close(self) -> None:
        if self.window is not None:
            self.window.orderOut_(None)
            self.window = None
