"""小さい画面では全体をスクロールし、下端の操作を失わないための器。"""
import tkinter as tk
from tkinter import ttk
from .theme import COLORS


class ScrollablePane(ttk.Frame):
    def __init__(self, master, minimum_width=1020, minimum_height=900):
        super().__init__(master)
        self.minimum_width = minimum_width
        self.minimum_height = minimum_height
        self.canvas = tk.Canvas(self, highlightthickness=0, background=COLORS['background'])
        self.vertical = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.horizontal = ttk.Scrollbar(self, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vertical.set, xscrollcommand=self.horizontal.set)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vertical.grid(row=0, column=1, sticky='ns')
        self.horizontal.grid(row=1, column=0, sticky='ew')
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.content = ttk.Frame(self.canvas)
        self.window = self.canvas.create_window(0, 0, anchor='nw', window=self.content)
        self.canvas.bind('<Configure>', self._resize)
        self.bind_all('<MouseWheel>', self._wheel, add='+')

    def _resize(self, event):
        width = max(event.width, self.minimum_width)
        height = max(event.height, self.minimum_height)
        self.canvas.itemconfigure(self.window, width=width, height=height)
        self.canvas.configure(scrollregion=(0, 0, width, height))
        # 余裕のある画面ではバーを隠し、通常の画面として表示する。
        if event.width < width:
            self.horizontal.grid()
        else:
            self.horizontal.grid_remove()
        if event.height < height:
            self.vertical.grid()
        else:
            self.vertical.grid_remove()

    def set_minimum_height(self, height):
        """画像プレビューが増えた時も下部の操作をスクロールで到達可能にする。"""
        self.minimum_height = height
        event = tk.Event()
        event.width = self.canvas.winfo_width()
        event.height = self.canvas.winfo_height()
        self._resize(event)

    def _wheel(self, event):
        """一覧や選択欄のホイール操作を奪わず、余白上だけ全体をスクロールする。"""
        if event.widget.winfo_class() in ('Treeview', 'TCombobox', 'Text', 'Listbox'):
            return
        widget = event.widget
        while widget is not None and widget is not self:
            widget = getattr(widget, 'master', None)
        if widget is self and self.canvas.winfo_height() < self.minimum_height:
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')
