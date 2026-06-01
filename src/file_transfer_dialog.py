# DualCPY - Dual-screen scrcpy docking and control UI for Windows
# Copyright (C) 2026 the_swest
# Contact: Github issues
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# src/file_transfer_dialog.py

import os
import re
import shlex
import string
import ctypes
import logging
import tempfile
import threading
import subprocess
import tkinter as tk
import customtkinter as ctk
from tkinter import ttk
from pathlib import Path
from PIL import Image, ImageTk

from src.win32_darkmode import enable_dark_titlebar
from src.ui_constants import (
    BG_COLOUR, PANEL_COLOUR, BORDER_COLOUR, TEXT_COLOUR,
    ACCENT_COLOUR, ACCENT2_COLOUR, TOP_COLOUR,
    SUCCESS_COLOUR, DANGER_COLOUR, WARNING_COLOUR,
    ICON_PATH, make_font, apply_window_icon, load_icon,
)

logger = logging.getLogger(__name__)

# ADB timeouts
ADB_LS_TIMEOUT      = 20
ADB_PUSH_TIMEOUT    = 600
ADB_PULL_TIMEOUT    = 600
ADB_MKDIR_TIMEOUT   = 15
ADB_PREVIEW_TIMEOUT = 30

CREATE_NO_WINDOW = 0x08000000

# UI sizing
DIALOG_WIDTH    = 1100
DIALOG_HEIGHT   = 720
PANE_MIN_WIDTH  = 360
PREVIEW_WIDTH   = 220
PREVIEW_HEIGHT  = 180

# File extensions we can display as images
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico"}

# Regex to extract file size from ls -la output
_LS_SIZE_RE = re.compile(r'^\S+\s+\d+\s+\S+\s+\S+\s+(\d+)\s+')

# Windows quick-nav shortcuts ("~" is expanded per-user at runtime, only locations that actually exist are shown)
WINDOWS_QUICK_PATHS = [
    ("~",            "Home"),
    ("~/Desktop",    "Desktop"),
    ("~/Downloads",  "Downloads"),
    ("~/Documents",  "Documents"),
    ("~/Pictures",   "Pictures"),
]

# Device quick-nav shortcuts
DEVICE_QUICK_PATHS = [
    ("/storage/emulated/0",           "Internal"),
    ("/storage/emulated/0/Download",  "Download"),
    ("/storage/emulated/0/DCIM",      "DCIM"),
    ("/storage/emulated/0/Pictures",  "Pictures"),
    ("/storage/emulated/0/Music",     "Music"),
    ("/storage/emulated/0/Documents", "Documents"),
]


# Helpers
def _fmt_size(size_bytes):
    if size_bytes < 0:
        return ""

    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024

    return f"{size_bytes:.1f} TB"


def _ext(name):
    return os.path.splitext(name)[1].lower()


def _dark_scrollbar(parent):
    """Return a styled scrollbar"""
    return tk.Scrollbar(
        parent,
        orient="vertical",
        troughcolor=PANEL_COLOUR,
        bg=BORDER_COLOUR,
        activebackground=ACCENT_COLOUR,
        highlightthickness=0,
        bd=0,
        width=10,
        relief="flat",
        elementborderwidth=0,
    )


def _run_adb(adb_bin, serial, args, timeout=ADB_LS_TIMEOUT):

    cmd = [adb_bin, "-s", serial] + args

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )

        return r.returncode, r.stdout, r.stderr

    except subprocess.TimeoutExpired:
        logger.warning(f"ADB timed out: {cmd}")
        return -1, "", "Timed out"

    except Exception as e:
        logger.error(f"ADB error: {e}")
        return -1, "", str(e)


def _run_adb_proc(adb_bin, serial, args):
    """Start an adb subprocess and return the Popen object for cancellable transfers"""

    cmd = [adb_bin, "-s", serial] + args

    return subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=CREATE_NO_WINDOW,
    )


def _unescape_ls(name):
    """Undo backslash-escaping that can cause issues with special characters."""
    result = []
    i = 0
    while i < len(name):
        if name[i] == "\\" and i + 1 < len(name):
            result.append(name[i + 1])
            i += 2
        else:
            result.append(name[i])
            i += 1
    return "".join(result)


# FileTransferDialog
class FileTransferDialog:
    """The actual file transfer dialog"""

    def __init__(self, parent, adb_bin, serial):
        self.parent = parent
        self.adb_bin = adb_bin
        self.serial  = serial

        self._win_cwd  = str(Path.home())
        self._dev_cwd  = "/storage/emulated/0"
        self._win_sel  = []
        self._dev_sel  = []
        self._transferring   = False
        self._preview_thread = None
        self._preview_image  = None

        self._dev_quick_frame = None

        self._build_window()

    # Window
    def _build_window(self):
        self.window = ctk.CTkToplevel(self.parent)
        self.window.withdraw()
        self.window.title("File Transfer - DualCPY")
        self.window.configure(fg_color=BG_COLOUR)
        self.window.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.window.minsize(PANE_MIN_WIDTH * 2 + 120, 520)
        self.window.resizable(True, True)

        # Dark titlebar
        self.window.after(80, self._apply_dark_titlebar)

        # ttk Treeview styling (used by the two file-list panes)
        self._init_tree_style()

        # Header
        hdr = ctk.CTkFrame(self.window, fg_color=PANEL_COLOUR, height=48)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="File Transfer",
            font=make_font(18, "bold"), text_color=ACCENT2_COLOUR,
        ).pack(side="left", padx=16, pady=10)

        self._status_lbl = ctk.CTkLabel(
            hdr, text="", font=make_font(12), text_color=TEXT_COLOUR,
        )
        self._status_lbl.pack(side="right", padx=16)

        # Progress bar
        self._progress_var = ctk.DoubleVar(value=0)
        self._progress_bar = ctk.CTkProgressBar(
            self.window, variable=self._progress_var,
            fg_color=BORDER_COLOUR, progress_color=ACCENT_COLOUR, height=4,
        )
        # packed dynamically in _start_transfer / _finish_transfer

        # Main area
        body = ctk.CTkFrame(self.window, fg_color=BG_COLOUR)
        body.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        body.columnconfigure(0, weight=1, minsize=PANE_MIN_WIDTH)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=1, minsize=PANE_MIN_WIDTH)
        body.rowconfigure(0, weight=1)

        self._win_frame = self._build_pane(body, col=0, label="Windows",
                                            label_colour=ACCENT2_COLOUR, is_device=False)
        self._build_transfer_column(body, col=1)
        self._dev_frame = self._build_pane(body, col=2, label="Device",
                                            label_colour=TOP_COLOUR, is_device=True)

        # Preview strip
        self._build_preview_strip()

        # Status bar
        foot = ctk.CTkFrame(self.window, fg_color=PANEL_COLOUR, height=28)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        ctk.CTkLabel(
            foot, text=f"Connected: {self.serial}",
            font=make_font(11), text_color=SUCCESS_COLOUR,
        ).pack(side="left", padx=12, pady=4)

        # Initial load
        self._refresh_win()
        self._refresh_dev()

        # Detect any SD cards and inject pill buttons asynchronously
        threading.Thread(target=self._detect_sd_cards, daemon=True).start()

        # apply_window_icon sets the icon now and re-applies it after CTk's ~200ms default-icon override
        self.window.update_idletasks()
        apply_window_icon(self.window)
        self.window.deiconify()

    # Treeview styling
    def _init_tree_style(self):
        """Dark ttk style for the two file list treeviews"""
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "DualCPY.Treeview",
            background=BG_COLOUR,
            fieldbackground=BG_COLOUR,
            foreground=TEXT_COLOUR,
            borderwidth=0,
            relief="flat",
            rowheight=24,
            font=("Consolas", 11),
        )

        style.map(
            "DualCPY.Treeview",
            background=[("selected", ACCENT_COLOUR)],
            foreground=[("selected", "#ffffff")],
        )

    # Row helpers
    @staticmethod
    def _tree_clear(tree):
        tree.delete(*tree.get_children())

    @staticmethod
    def _tree_row(tree, idx, icon_name, text):
        """Selectable file/folder row"""
        tree.insert("", "end", iid=str(idx), text=" " + text,
                    image=(load_icon(icon_name, 16) or ""))

    @staticmethod
    def _tree_status(tree, icon_name, text):
        # placeholder/error row, its auto iid isnt numeric so _selected_indices() just skips it
        tree.insert("", "end", text=" " + text,
                    image=(load_icon(icon_name, 16) or ""))

    @staticmethod
    def _selected_indices(tree):
        """Selected row indices, skipping the status/placeholder rows"""
        return [int(i) for i in tree.selection() if i.isdigit()]

    # Pane builder
    def _build_pane(self, parent, col, label, label_colour, is_device):
        outer = ctk.CTkFrame(parent, fg_color=PANEL_COLOUR, corner_radius=8)
        outer.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        # Label
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))
        ctk.CTkLabel(hdr, text=label, font=make_font(14, "bold"),
                     text_color=label_colour).pack(side="left")

        # Nav row
        nav = ctk.CTkFrame(outer, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        nav.columnconfigure(1, weight=1)

        ctk.CTkButton(
            nav, text="Up", image=load_icon("up", 14, "ctk"), compound="left",
            width=60, height=26,
            fg_color=BORDER_COLOUR, hover_color=ACCENT_COLOUR,
            font=make_font(12),
            command=self._win_up if not is_device else self._dev_up,
        ).grid(row=0, column=0, padx=(0, 4))

        if is_device:
            self._dev_path_var = ctk.StringVar(value=self._dev_cwd)
            e = ctk.CTkEntry(nav, textvariable=self._dev_path_var,
                             fg_color=BG_COLOUR, border_color=BORDER_COLOUR,
                             text_color=TEXT_COLOUR, font=make_font(11), height=26)

            e.grid(row=0, column=1, sticky="ew", padx=(0, 4))
            e.bind("<Return>", lambda _: self._dev_navigate(self._dev_path_var.get()))

            ctk.CTkButton(nav, text="Go", width=40, height=26,
                          fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
                          font=make_font(12),
                          command=lambda: self._dev_navigate(self._dev_path_var.get()),
                          ).grid(row=0, column=2)

        else:
            self._win_path_var = ctk.StringVar(value=self._win_cwd)

            e = ctk.CTkEntry(nav, textvariable=self._win_path_var,
                             fg_color=BG_COLOUR, border_color=BORDER_COLOUR,
                             text_color=TEXT_COLOUR, font=make_font(11), height=26)

            e.grid(row=0, column=1, sticky="ew", padx=(0, 4))
            e.bind("<Return>", lambda _: self._win_navigate(self._win_path_var.get()))

            ctk.CTkButton(nav, text="Go", width=40, height=26,
                          fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
                          font=make_font(12),
                          command=lambda: self._win_navigate(self._win_path_var.get()),
                          ).grid(row=0, column=2)

        # Quick-nav pills
        quick = ctk.CTkFrame(outer, fg_color="transparent")
        quick.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        if is_device:
            for path, short in DEVICE_QUICK_PATHS:
                ctk.CTkButton(
                    quick, text=short, width=72, height=22,
                    fg_color=BG_COLOUR, hover_color=BORDER_COLOUR,
                    text_color=TEXT_COLOUR, font=make_font(10),
                    command=lambda p=path: self._dev_navigate(p),
                ).pack(side="left", padx=2)

            # Keep a ref so SD-card pills can be injected later
            self._dev_quick_frame = quick

        else:
            self._populate_drive_buttons(quick)

        # Listbox + dark scrollbar
        list_frame = ctk.CTkFrame(outer, fg_color=BG_COLOUR, corner_radius=6)
        list_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(0, 4))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        sb = _dark_scrollbar(list_frame)
        sb.grid(row=0, column=1, sticky="ns")

        lb = ttk.Treeview(
            list_frame,
            show="tree",
            selectmode="extended",
            style="DualCPY.Treeview",
            yscrollcommand=sb.set,
        )

        lb.column("#0", stretch=True)
        lb.grid(row=0, column=0, sticky="nsew")
        sb.config(command=lb.yview)

        if is_device:
            self._dev_lb = lb
            lb.bind("<Double-Button-1>", self._dev_double_click)
            lb.bind("<<TreeviewSelect>>", self._dev_on_select)

        else:
            self._win_lb = lb
            lb.bind("<Double-Button-1>", self._win_double_click)
            lb.bind("<<TreeviewSelect>>", self._win_on_select)

        # Footer
        footer = ctk.CTkFrame(outer, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 6))

        if is_device:
            self._dev_sel_lbl = ctk.CTkLabel(footer, text="", font=make_font(11), text_color=TEXT_COLOUR)
            self._dev_sel_lbl.pack(side="left")

            ctk.CTkButton(footer, text="Delete",
                          image=load_icon("delete", 14, "ctk"), compound="left",
                          width=80, height=24,
                          fg_color=BORDER_COLOUR, hover_color=DANGER_COLOUR,
                          font=make_font(11), command=self._dev_delete,
                          ).pack(side="right", padx=(2, 0))

            ctk.CTkButton(footer, text="Rename",
                          image=load_icon("rename", 14, "ctk"), compound="left",
                          width=80, height=24,
                          fg_color=BORDER_COLOUR, hover_color=ACCENT_COLOUR,
                          font=make_font(11), command=self._dev_rename,
                          ).pack(side="right", padx=2)

            ctk.CTkButton(footer, text="Folder",
                          image=load_icon("new_folder", 14, "ctk"), compound="left",
                          width=76, height=24,
                          fg_color=BORDER_COLOUR, hover_color=ACCENT_COLOUR,
                          font=make_font(11), command=self._dev_new_folder,
                          ).pack(side="right", padx=2)

        else:
            self._win_sel_lbl = ctk.CTkLabel(footer, text="", font=make_font(11), text_color=TEXT_COLOUR)
            self._win_sel_lbl.pack(side="left")

        return outer

    # Transfer button column
    def _build_transfer_column(self, parent, col):
        mid = ctk.CTkFrame(parent, fg_color="transparent", width=56)
        mid.grid(row=0, column=col, sticky="ns", padx=0, pady=4)
        mid.pack_propagate(False)
        mid.rowconfigure(0, weight=1)
        mid.rowconfigure(4, weight=1)

        self._push_btn = ctk.CTkButton(
            mid, text="Push", image=load_icon("push", 18, "ctk"), compound="top",
            width=52, height=56,
            fg_color=ACCENT_COLOUR, hover_color=ACCENT2_COLOUR,
            font=make_font(11, "bold"), command=self._push_selected,
        )

        self._push_btn.grid(row=1, column=0, pady=4)

        self._pull_btn = ctk.CTkButton(
            mid, text="Pull", image=load_icon("pull", 18, "ctk"), compound="top",
            width=52, height=56,
            fg_color="#1a4a2e", hover_color=SUCCESS_COLOUR,
            font=make_font(11, "bold"), command=self._pull_selected,
        )

        self._pull_btn.grid(row=2, column=0, pady=4)

        self._cancel_btn = ctk.CTkButton(
            mid, text="Stop", image=load_icon("stop", 16, "ctk"), compound="top",
            width=52, height=40,
            fg_color=DANGER_COLOUR, hover_color="#c0392b",
            font=make_font(11, "bold"), command=self._cancel_transfer,
        )

        # shown only during a transfer
        self._cancel_btn.grid(row=3, column=0, pady=4)
        self._cancel_btn.grid_remove()

    # Preview strip
    def _build_preview_strip(self):
        """Horizontal strip below the panes"""
        self._preview_frame = ctk.CTkFrame(
            self.window, fg_color=PANEL_COLOUR, height=PREVIEW_HEIGHT + 20,
        )

        self._preview_frame.pack(fill="x", padx=6, pady=(0, 4))
        self._preview_frame.pack_propagate(False)
        self._preview_frame.columnconfigure(1, weight=1)

        thumb_container = tk.Frame(
            self._preview_frame,
            width=PREVIEW_WIDTH, height=PREVIEW_HEIGHT,
            bg=BG_COLOUR,
        )

        thumb_container.grid(row=0, column=0, padx=(8, 6), pady=8, sticky="ns")
        thumb_container.pack_propagate(False)
        thumb_container.grid_propagate(False)

        self._thumb_lbl = tk.Label(
            thumb_container,
            text="",
            bg=BG_COLOUR, fg=TEXT_COLOUR,
            relief="flat", bd=0,
            font=("Segoe UI Emoji", 36),
            anchor="center",
        )
        # Fill the container via place so the label never drives its own size
        self._thumb_lbl.place(relwidth=1, relheight=1)

        # Metadata text
        self._meta_lbl = ctk.CTkLabel(
            self._preview_frame,
            text="Select a file to preview",
            font=make_font(12),
            text_color=BORDER_COLOUR,
            anchor="nw",
            justify="left",
            wraplength=500,
        )

        self._meta_lbl.grid(row=0, column=1, padx=8, pady=8, sticky="nw")

    def _clear_preview(self):
        self._thumb_lbl.configure(image="", text="")
        self._meta_lbl.configure(text="Select a file to preview", text_color=BORDER_COLOUR)
        self._preview_image = None

    def _set_thumb_icon(self, icon_name, text="", size=72):
        """Show a static icon (loading / failed / file-type) in the preview thumb,
        falls back to plain text if the asset isnt there yet"""
        img = load_icon(icon_name, size, "tk")
        self._preview_image = img

        if img is not None:
            self._thumb_lbl.configure(
                image=img, text=text, compound="top" if text else "center",
            )

        else:
            self._thumb_lbl.configure(image="", text=text)

    def _show_preview_win(self, name):
        """Show preview for a Windows-side file."""
        path = os.path.join(self._win_cwd, name)

        try:
            stat = os.stat(path)
            meta = f"{name}\n\nSize: {_fmt_size(stat.st_size)}\nPath: {path}"

        except Exception:
            meta = name

        self._meta_lbl.configure(text=meta, text_color=TEXT_COLOUR)

        if _ext(name) in IMAGE_EXTS:
            self._set_thumb_icon("loading")
            threading.Thread(target=self._load_image_win, args=(path,), daemon=True).start()

        else:
            self._set_thumb_icon(_file_type_icon_name(name))

    def _load_image_win(self, path):
        try:
            from PIL import Image, ImageTk
            img = Image.open(path)
            img.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT))
            tk_img = ImageTk.PhotoImage(img)
            self.window.after(0, self._apply_thumb, tk_img)

        except Exception as e:
            logger.debug(f"Win preview failed for {path}: {e}")
            self.window.after(0, self._set_thumb_icon, "warning", "Preview\nfailed")

    def _show_preview_dev(self, name):
        """Show preview for a device-side file (pull to temp for images)."""
        remote = self._dev_cwd.rstrip("/") + "/" + name
        self._meta_lbl.configure(
            text=f"{name}\n\nDevice path: {remote}", text_color=TEXT_COLOUR
        )

        if _ext(name) in IMAGE_EXTS:
            self._set_thumb_icon("loading")

            threading.Thread(
                target=self._load_image_dev, args=(remote, name), daemon=True
            ).start()

        else:
            self._set_thumb_icon(_file_type_icon_name(name))

    def _load_image_dev(self, remote, name):
        tmp = None
        try:
            tmp = tempfile.mktemp(suffix=_ext(name), prefix="dualcpy_preview_")

            rc, _, err = _run_adb(
                self.adb_bin, self.serial,
                ["pull", remote, tmp],
                timeout=ADB_PREVIEW_TIMEOUT,
            )

            if rc != 0:
                raise RuntimeError(err.strip())

            img = Image.open(tmp)
            img.thumbnail((PREVIEW_WIDTH, PREVIEW_HEIGHT))
            tk_img = ImageTk.PhotoImage(img)
            self.window.after(0, self._apply_thumb, tk_img)

        except Exception as e:
            logger.debug(f"Dev preview failed for {remote}: {e}")
            self.window.after(0, self._set_thumb_icon, "warning", "Preview\nfailed")

        finally:
            if tmp:
                try:
                    os.remove(tmp)

                except Exception:
                    pass

    def _apply_thumb(self, tk_img):
        self._preview_image = tk_img
        self._thumb_lbl.configure(image=tk_img, text="")

    # SD card detection
    def _detect_sd_cards(self):
        """
        List /storage/ on the device and adds a pill button for every volume that isn't internal storage
        """
        rc, out, _ = _run_adb(
            self.adb_bin, self.serial,
            ["shell", "ls", "/storage/"],
            timeout=ADB_LS_TIMEOUT,
        )

        if rc != 0:
            return

        for name in out.split():
            name = name.strip().rstrip("/")

            if not name or name.lower() in ("emulated", "self", "sdcard"):
                continue

            path = f"/storage/{name}"
            short = name if len(name) <= 9 else "SD"
            self.window.after(0, self._add_sd_pill, path, short)

    def _add_sd_pill(self, path, label):
        """Add a quick-nav pill for an SD card volume."""
        if self._dev_quick_frame is None:
            return

        ctk.CTkButton(
            self._dev_quick_frame,
            text=label, image=load_icon("sdcard", 12, "ctk"), compound="left",
            width=80, height=22,
            fg_color="#1a3a1a", hover_color="#2d5a2d",
            text_color=TEXT_COLOUR, font=make_font(10),
            command=lambda p=path: self._dev_navigate(p),
        ).pack(side="left", padx=2)

    # Windows pane navigation & selection
    def _populate_drive_buttons(self, parent):
        # Preset locations first
        for raw, label in WINDOWS_QUICK_PATHS:
            path = os.path.normpath(os.path.expanduser(raw))

            if os.path.isdir(path):
                ctk.CTkButton(
                    parent, text=label, width=64, height=22,
                    fg_color=BG_COLOUR, hover_color=BORDER_COLOUR,
                    text_color=TEXT_COLOUR, font=make_font(10),
                    command=lambda p=path: self._win_navigate(p),
                ).pack(side="left", padx=2)

        # Then the drive letters
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                ctk.CTkButton(
                    parent, text=f"{letter}:", width=36, height=22,
                    fg_color=BG_COLOUR, hover_color=BORDER_COLOUR,
                    text_color=TEXT_COLOUR, font=make_font(10),
                    command=lambda d=drive: self._win_navigate(d),
                ).pack(side="left", padx=2)

    def _refresh_win(self):
        if not hasattr(self, "_win_path_var"):
            return

        self._win_path_var.set(self._win_cwd)
        self._tree_clear(self._win_lb)
        self._win_sel.clear()
        self._win_sel_lbl.configure(text="")

        try:
            entries = sorted(
                os.scandir(self._win_cwd),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )

        except PermissionError:
            self._tree_status(self._win_lb, "warning", "Access denied")
            return

        except Exception as ex:
            self._tree_status(self._win_lb, "warning", str(ex))
            return

        self._win_entries = []
        self._win_is_dir  = []

        for entry in entries:
            idx = len(self._win_entries)
            try:
                is_dir = entry.is_dir()

                if is_dir:
                    self._tree_row(self._win_lb, idx, "folder", f"{entry.name}/")

                else:
                    size = entry.stat().st_size
                    self._tree_row(self._win_lb, idx,
                                   _file_type_icon_name(entry.name),
                                   f"{entry.name}  ({_fmt_size(size)})")

                self._win_entries.append(entry.name)
                self._win_is_dir.append(is_dir)

            except Exception:
                self._tree_row(self._win_lb, idx, "file", entry.name)
                self._win_entries.append(entry.name)
                self._win_is_dir.append(False)

    def _win_navigate(self, path):
        path = path.strip()

        if os.path.isdir(path):
            self._win_cwd = path
            self._clear_preview()
            self._refresh_win()

        else:
            self._set_status(f"Not a directory: {path}", "error")

    def _win_up(self):
        p = str(Path(self._win_cwd).parent)

        if p != self._win_cwd:
            self._win_navigate(p)

    def _win_double_click(self, event):
        iid = self._win_lb.identify_row(event.y)

        if not iid or not iid.isdigit():
            return

        idx = int(iid)

        if idx < len(self._win_is_dir) and self._win_is_dir[idx]:
            self._win_navigate(os.path.join(self._win_cwd, self._win_entries[idx]))

    def _win_on_select(self, _event):
        idxs = self._selected_indices(self._win_lb)
        self._win_sel = [self._win_entries[i] for i in idxs if i < len(self._win_entries)]
        count = len(self._win_sel)
        self._win_sel_lbl.configure(text=f"{count} selected" if count else "")

        # Preview single selection
        if len(self._win_sel) == 1:
            idx = idxs[0]
            if idx < len(self._win_is_dir) and not self._win_is_dir[idx]:
                self._show_preview_win(self._win_sel[0])
                return

        self._clear_preview()

    # Device pane: navigation & selection
    def _refresh_dev(self):
        if not hasattr(self, "_dev_path_var"):
            return

        self._dev_path_var.set(self._dev_cwd)
        self._tree_clear(self._dev_lb)
        self._dev_sel.clear()
        self._dev_sel_lbl.configure(text="")
        self._dev_entries = []
        self._dev_is_dir  = []
        self._tree_status(self._dev_lb, "loading", "Loading...")
        self.window.update_idletasks()

        threading.Thread(
            target=self._fetch_dev_listing, args=(self._dev_cwd,), daemon=True
        ).start()

    def _fetch_dev_listing(self, path):
        quoted = shlex.quote(path)

        # Names + is_dir from ls -1pL
        rc, out, err = _run_adb(
            self.adb_bin, self.serial,
            ["shell", f"ls -1pL {quoted}"],
            timeout=ADB_LS_TIMEOUT,
        )

        if rc != 0:
            self.window.after(0, self._populate_dev_lb, None,
                              err.strip() or f"exit {rc}")
            return

        name_list = []

        for line in out.splitlines():
            line = line.rstrip("\r")

            if not line:
                continue

            is_dir = line.endswith("/")
            name   = _unescape_ls(line.rstrip("/"))

            if name in (".", ".."):
                continue

            name_list.append((name, is_dir))

        # Sizes via ls -la
        size_map = {}

        rc2, out2, _ = _run_adb(
            self.adb_bin, self.serial,
            ["shell", f"ls -la {quoted}"],
            timeout=ADB_LS_TIMEOUT,
        )

        if rc2 == 0:
            for line in out2.splitlines():
                line = line.strip()

                if not line or line.startswith("total"):
                    continue

                m = _LS_SIZE_RE.match(line)

                if not m:
                    continue

                try:
                    sz = int(m.group(1))
                except ValueError:
                    continue
                # split(None, 7) -> [perms, links, user, group, size, date, time, name+]
                # index 7 is the full filename, preserving any spaces within it.
                parts = line.split(None, 7)

                if len(parts) < 8:
                    continue

                raw_name = _unescape_ls(parts[7].split(" -> ")[0] if " -> " in parts[7] else parts[7])

                if raw_name not in (".", ".."):
                    size_map[raw_name] = sz

        entries = [
            (name, is_dir, size_map.get(name, -1))
            for name, is_dir in name_list
        ]

        entries.sort(key=lambda x: (not x[1], x[0].lower()))
        self.window.after(0, self._populate_dev_lb, entries, None)

    def _populate_dev_lb(self, entries, errmsg):
        self._tree_clear(self._dev_lb)
        if entries is None:
            # Also clear the arrays on error so a double-click can't navigate somewhere wrong
            self._dev_entries = []
            self._dev_is_dir  = []
            self._tree_status(self._dev_lb, "warning", errmsg)
            return

        self._dev_entries = [e[0] for e in entries]
        self._dev_is_dir  = [e[1] for e in entries]

        for idx, (name, is_dir, size) in enumerate(entries):
            if is_dir:
                self._tree_row(self._dev_lb, idx, "folder", f"{name}/")
            else:
                sz = f"  ({_fmt_size(size)})" if size >= 0 else ""
                self._tree_row(self._dev_lb, idx,
                               _file_type_icon_name(name), f"{name}{sz}")

        if not entries:
            self._tree_status(self._dev_lb, "file", "(empty)")

    def _dev_navigate(self, path):
        self._dev_cwd = path.rstrip("/") or "/"
        self._clear_preview()
        self._refresh_dev()

    def _dev_up(self):
        p = str(Path(self._dev_cwd).parent).replace("\\", "/")

        if p != self._dev_cwd:
            self._dev_navigate(p)

    def _dev_double_click(self, event):
        iid = self._dev_lb.identify_row(event.y)

        if not iid or not iid.isdigit():
            return

        idx = int(iid)

        if not hasattr(self, "_dev_is_dir") or idx >= len(self._dev_is_dir):
            return

        if self._dev_is_dir[idx]:
            self._dev_navigate(self._dev_cwd.rstrip("/") + "/" + self._dev_entries[idx])

    def _dev_on_select(self, _event):
        idxs = self._selected_indices(self._dev_lb)

        if hasattr(self, "_dev_entries"):
            self._dev_sel = [self._dev_entries[i] for i in idxs if i < len(self._dev_entries)]

        count = len(self._dev_sel)
        self._dev_sel_lbl.configure(text=f"{count} selected" if count else "")

        # Preview single selection
        if len(self._dev_sel) == 1 and hasattr(self, "_dev_is_dir"):
            idx = idxs[0]

            if idx < len(self._dev_is_dir) and not self._dev_is_dir[idx]:
                self._show_preview_dev(self._dev_sel[0])
                return

        self._clear_preview()

    def _dev_new_folder(self):
        dlg = _InputDialog(self.window, "New Folder", "Folder name:")
        name = dlg.get()

        if not name:
            return

        path = self._dev_cwd.rstrip("/") + "/" + name
        rc, _, err = _run_adb(self.adb_bin, self.serial,
                               ["shell", f"mkdir -p {shlex.quote(path)}"],
                               timeout=ADB_MKDIR_TIMEOUT)

        if rc == 0:
            self._set_status(f"Created {name}", "success")
            self._refresh_dev()
        else:
            self._set_status(f"mkdir failed: {err.strip()}", "error")

    def _dev_rename(self):
        if not self._dev_sel:
            self._set_status("Select a file or folder to rename", "warning")
            return

        if len(self._dev_sel) > 1:
            self._set_status("Select only one item to rename", "warning")
            return

        old_name = self._dev_sel[0]
        dlg = _InputDialog(self.window, "Rename", f"New name for '{old_name}':")
        new_name = dlg.get()

        if not new_name or new_name == old_name:
            return

        old_path = self._dev_cwd.rstrip("/") + "/" + old_name
        new_path = self._dev_cwd.rstrip("/") + "/" + new_name

        rc, _, err = _run_adb(
            self.adb_bin, self.serial,
            ["shell", f"mv {shlex.quote(old_path)} {shlex.quote(new_path)}"],
            timeout=ADB_MKDIR_TIMEOUT,
        )

        if rc == 0:
            self._set_status(f"Renamed '{old_name}' -> '{new_name}'", "success")
            self._refresh_dev()
        else:
            self._set_status(f"Rename failed: {err.strip()}", "error")

    def _dev_delete(self):
        if not self._dev_sel:
            self._set_status("Select file(s) or folder(s) to delete", "warning")
            return

        # Confirmation dialog
        count   = len(self._dev_sel)
        subject = f"'{self._dev_sel[0]}'" if count == 1 else f"{count} items"

        confirm = _ConfirmDialog(
            self.window,
            title="Confirm Delete",
            message=f"Permanently delete {subject} from the device?\nThis cannot be undone.",
        )

        if not confirm.get():
            return

        errors = []

        for name in self._dev_sel:
            path = self._dev_cwd.rstrip("/") + "/" + name

            rc, _, err = _run_adb(
                self.adb_bin, self.serial,
                ["shell", f"rm -rf {shlex.quote(path)}"],
                timeout=ADB_MKDIR_TIMEOUT,
            )

            if rc != 0:
                errors.append(f"{name}: {err.strip() or f'exit {rc}'}")

        if errors:
            self._set_status(f"Delete failed: {errors[0]}", "error")
            logger.error(f"Device delete errors: {errors}")
        else:
            self._set_status(
                f"Deleted {count} item(s)" if count > 1 else f"Deleted '{self._dev_sel[0]}'",
                "success",
            )

        self._refresh_dev()

    # Transfer
    def _push_selected(self):
        if not self._win_sel:
            self._set_status("Select file(s) on the Windows side first", "warning")
            return

        if self._transferring:
            return

        files   = [os.path.join(self._win_cwd, n) for n in self._win_sel
                   if not self._win_is_dir[self._win_entries.index(n)]]
        folders = [n for n in self._win_sel
                   if self._win_is_dir[self._win_entries.index(n)]]

        if folders:
            self._set_status("Folders skipped - files only", "warning")

        if not files:
            self._set_status("No files selected for push", "warning")
            return

        self._start_transfer(f"Pushing {len(files)} file(s)...",
                             self._do_push, (files, self._dev_cwd))

    def _pull_selected(self):
        if not self._dev_sel:
            self._set_status("Select file(s) on the Device side first", "warning")
            return

        if self._transferring:
            return

        names = [n for n in self._dev_sel
                 if not self._dev_is_dir[self._dev_entries.index(n)]]

        if len(names) < len(self._dev_sel):
            self._set_status("Folders skipped - files only", "warning")

        if not names:
            self._set_status("No files selected for pull", "warning")
            return

        remote_paths = [self._dev_cwd.rstrip("/") + "/" + n for n in names]
        self._start_transfer(f"Pulling {len(remote_paths)} file(s)...",
                             self._do_pull, (remote_paths, self._win_cwd))

    def _start_transfer(self, label, fn, args):
        self._transferring   = True
        self._cancel_flag    = False
        self._active_proc    = None
        self._set_status(label, "info")
        self._progress_bar.pack(fill="x", padx=8, pady=0)
        self._progress_var.set(0)
        self._push_btn.configure(state="disabled")
        self._pull_btn.configure(state="disabled")
        self._cancel_btn.grid()
        threading.Thread(target=self._transfer_worker, args=(fn, args), daemon=True).start()

    def _cancel_transfer(self):
        """Tell the transfer thread to stop after the current file"""
        self._cancel_flag = True
        proc = self._active_proc

        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

        self._set_status("Cancelling...", "warning")

    def _transfer_worker(self, fn, args):
        try:
            fn(*args)
        except Exception as e:
            logger.error(f"Transfer error: {e}", exc_info=True)
            self.window.after(0, self._set_status, f"Transfer error: {e}", "error")
        finally:
            self.window.after(0, self._finish_transfer)

    def _finish_transfer(self):
        self._transferring = False
        self._active_proc  = None
        self._progress_bar.pack_forget()
        self._push_btn.configure(state="normal")
        self._pull_btn.configure(state="normal")
        self._cancel_btn.grid_remove()
        self._refresh_win()
        self._refresh_dev()

    def _do_push(self, local_files, remote_dir):
        total = len(local_files)
        done  = 0
        for i, local in enumerate(local_files):
            if self._cancel_flag:
                self.window.after(0, self._set_status,
                                  f"Cancelled after {done}/{total} file(s)", "warning")
                return

            name   = os.path.basename(local)
            remote = remote_dir.rstrip("/") + "/" + name
            self.window.after(0, self._set_status,
                              f"Pushing {name} ({i+1}/{total})...", "info")
            self.window.after(0, self._progress_var.set, i / total)
            proc = _run_adb_proc(self.adb_bin, self.serial, ["push", local, remote])
            self._active_proc = proc
            timed_out = False

            try:
                _out, _err = proc.communicate(timeout=ADB_PUSH_TIMEOUT)
                stdout = _out.decode("utf-8", errors="replace")
                stderr = _err.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                timed_out = True

            if timed_out or self._cancel_flag:
                # Remove the partial file from the device
                _run_adb(self.adb_bin, self.serial,
                         ["shell", f"rm -f {shlex.quote(remote)}"],
                         timeout=ADB_LS_TIMEOUT)
                msg = f"Push timed out: {name}" if timed_out else f"Cancelled after {done}/{total} file(s)"
                kind = "error" if timed_out else "warning"
                self.window.after(0, self._set_status, msg, kind)
                return

            rc = proc.returncode

            if rc != 0:
                # Clean up any partial file left on device
                _run_adb(self.adb_bin, self.serial,
                         ["shell", f"rm -f {shlex.quote(remote)}"],
                         timeout=ADB_LS_TIMEOUT)
                msg = stderr.strip() or stdout.strip() or f"exit {rc}"
                self.window.after(0, self._set_status, f"Push failed: {msg}", "error")
                logger.error(f"Push failed {local}: {msg}")
                return

            done += 1
            self.window.after(0, self._progress_var.set, done / total)
            logger.info(f"Pushed: {local} -> {remote}")

        self.window.after(0, self._set_status,
                          f"Pushed {total} file(s) successfully", "success")
        self.window.after(0, self._progress_var.set, 1.0)

    def _do_pull(self, remote_files, local_dir):
        total = len(remote_files)
        done  = 0

        for i, remote in enumerate(remote_files):
            if self._cancel_flag:
                self.window.after(0, self._set_status,
                                  f"Cancelled after {done}/{total} file(s)", "warning")
                return

            name  = remote.split("/")[-1]
            local = os.path.join(local_dir, name)
            self.window.after(0, self._set_status,
                              f"Pulling {name} ({i+1}/{total})...", "info")
            self.window.after(0, self._progress_var.set, i / total)
            proc = _run_adb_proc(self.adb_bin, self.serial, ["pull", remote, local])
            self._active_proc = proc
            timed_out = False

            try:
                _out, _err = proc.communicate(timeout=ADB_PULL_TIMEOUT)
                stdout = _out.decode("utf-8", errors="replace")
                stderr = _err.decode("utf-8", errors="replace")
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                timed_out = True

            if timed_out or self._cancel_flag:
                # Remove the partial file from Windows
                try:
                    if os.path.exists(local):
                        os.remove(local)
                        logger.info(f"Removed partial file: {local}")
                except OSError as e:
                    logger.warning(f"Could not remove partial file {local}: {e}")

                msg = f"Pull timed out: {name}" if timed_out else f"Cancelled after {done}/{total} file(s)"
                kind = "error" if timed_out else "warning"
                self.window.after(0, self._set_status, msg, kind)
                return

            rc = proc.returncode

            if rc != 0:
                # Clean up any partial file left on Windows
                try:
                    if os.path.exists(local):
                        os.remove(local)
                        logger.info(f"Removed partial file: {local}")
                except OSError as e:
                    logger.warning(f"Could not remove partial file {local}: {e}")

                msg = stderr.strip() or stdout.strip() or f"exit {rc}"
                self.window.after(0, self._set_status, f"Pull failed: {msg}", "error")
                logger.error(f"Pull failed {remote}: {msg}")
                return

            done += 1
            self.window.after(0, self._progress_var.set, done / total)
            logger.info(f"Pulled: {remote} -> {local}")

        self.window.after(0, self._set_status,
                          f"Pulled {total} file(s) successfully", "success")
        self.window.after(0, self._progress_var.set, 1.0)

    # Helpers
    def _set_status(self, msg, kind="info"):
        colour_map = {
            "success": SUCCESS_COLOUR,
            "error":   DANGER_COLOUR,
            "warning": WARNING_COLOUR,
            "info":    TEXT_COLOUR,
        }

        self._status_lbl.configure(text=msg, text_color=colour_map.get(kind, TEXT_COLOUR))
        logger.debug(f"FileTransfer [{kind}]: {msg}")

    def _apply_dark_titlebar(self):
        try:
            self.window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id()) or self.window.winfo_id()
            enable_dark_titlebar(hwnd)
        except Exception:
            pass

    def show(self):
        self.window.lift()
        self.window.focus_force()


# File-type icon helper
_TYPE_ICON_NAMES = {
    ".pdf":  "pdf",
    ".zip":  "archive",
    ".rar":  "archive",
    ".7z":   "archive",
    ".mp4":  "video",
    ".mkv":  "video",
    ".avi":  "video",
    ".mov":  "video",
    ".mp3":  "audio",
    ".flac": "audio",
    ".wav":  "audio",
    ".ogg":  "audio",
    ".apk":  "package",
    ".txt":  "text",
    ".log":  "text",
    ".json": "text",
    ".xml":  "text",
}


def _file_type_icon_name(name):
    """The assets/icons/ icon name for a file, minus the extension"""
    ext = _ext(name)

    if ext in IMAGE_EXTS:
        return "image"

    return _TYPE_ICON_NAMES.get(ext, "file")


# Inline input dialog
class _InputDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, prompt):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=PANEL_COLOUR)
        self.resizable(False, False)
        self.grab_set()
        apply_window_icon(self)

        ctk.CTkLabel(self, text=prompt, font=make_font(13),
                     text_color=TEXT_COLOUR).pack(padx=20, pady=(16, 4))

        self._var = ctk.StringVar()
        entry = ctk.CTkEntry(self, textvariable=self._var, width=240, font=make_font(12))
        entry.pack(padx=20, pady=4)
        entry.focus_set()
        entry.bind("<Return>", lambda _: self._ok())

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(8, 16))

        ctk.CTkButton(row, text="OK", width=80, fg_color=ACCENT_COLOUR,
                      command=self._ok).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Cancel", width=80, fg_color=BORDER_COLOUR,
                      command=self._cancel).pack(side="left", padx=4)

        self._result = None
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.wait_window()

    def _ok(self):
        self._result = self._var.get().strip()
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get(self):
        return self._result

class _ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.title(title)
        self.configure(fg_color=PANEL_COLOUR)
        self.resizable(False, False)
        self.grab_set()
        apply_window_icon(self)

        ctk.CTkLabel(self, text=message, font=make_font(13),
                     text_color=TEXT_COLOUR, justify="center",
                     wraplength=320).pack(padx=24, pady=(20, 12))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(0, 18))
        ctk.CTkButton(row, text="Delete", width=90, fg_color=DANGER_COLOUR,
                      hover_color="#c0392b", command=self._yes).pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancel", width=90, fg_color=BORDER_COLOUR,
                      command=self._no).pack(side="left", padx=6)

        self._result = False
        self.protocol("WM_DELETE_WINDOW", self._no)
        self.wait_window()

    def _yes(self):
        self._result = True
        self.destroy()

    def _no(self):
        self._result = False
        self.destroy()

    def get(self):
        return self._result