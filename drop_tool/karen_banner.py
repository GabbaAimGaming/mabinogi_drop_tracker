"""利用者提供のカレン画像を保ったまま、指先と撮影ボタンの位置を揃える。"""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from .config import ROOT


class KarenBanner(tk.Canvas):
    """通常の子ウィジェットとして配置。別窓や最前面の装飾は使わない。"""

    def __init__(self, master, command):
        super().__init__(master, width=340, height=120, highlightthickness=0, background='#FFF6F4')
        with Image.open(ROOT / 'assets/karen.png') as image:
            # 透過PNGをそのまま表示。背景除去や描き直しはしない。
            self.photo = ImageTk.PhotoImage(image.convert('RGBA').resize((90, 120), Image.Resampling.LANCZOS))
        self.button = ttk.Button(self, text='5秒後に報酬を読取', style='Accent.TButton', command=command)
        self.button_item = self.create_window(0, 10, anchor='ne', window=self.button, width=218, height=36)
        self.character = self.create_image(0, 0, image=self.photo, anchor='nw')
        self.bind('<Configure>', self._layout)

    def _layout(self, event):
        """指先は画像左上から約(6,27)。ボタンの右下へ向く間隔を保つ。"""
        self.coords(self.character, event.width - 100, 0)
        self.coords(self.button_item, event.width - 112, 3)
