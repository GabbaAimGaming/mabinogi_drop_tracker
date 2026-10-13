"""カレンの赤髪とメイド服に合わせた、淡いローズとクリームの配色。"""
from tkinter import ttk

COLORS = dict(background='#FFF6F4', panel='#FFFAF8', rose='#F5D4D9',
              accent='#AB3D56', text='#57383E', muted='#88666C', white='#FFFFFF')


def apply_theme(root):
    """描画テーマのOS差を抑え、選択色と文字の読みやすさも統一する。"""
    c = COLORS
    root.configure(background=c['background'])
    root.option_add('*Font', ('Yu Gothic UI', 10))
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('.', background=c['background'], foreground=c['text'], font=('Yu Gothic UI', 10))
    style.configure('TFrame', background=c['background'])
    style.configure('TLabel', background=c['background'], foreground=c['text'])
    style.configure('TButton', background='#FBE5E8', foreground=c['text'],
                    bordercolor='#EAC4CB', lightcolor='#FFF8F6', darkcolor='#EAC4CB', padding=(10, 6))
    style.map('TButton', background=[('active', '#F5CCD5'), ('pressed', '#EDB4C2')],
              foreground=[('disabled', '#B89CA1')])
    style.configure('Accent.TButton', background=c['accent'], foreground='white',
                    font=('Yu Gothic UI', 10, 'bold'), bordercolor=c['accent'])
    style.map('Accent.TButton', background=[('active', '#C34E67'), ('pressed', '#8F2C43')],
              foreground=[('disabled', '#E0BDC5'), ('!disabled', 'white')])
    style.configure('TEntry', fieldbackground=c['white'], bordercolor='#E8C6CC', padding=4)
    style.configure('TCombobox', fieldbackground=c['white'], arrowcolor=c['accent'], padding=4)
    style.map('TCombobox', fieldbackground=[('readonly', c['white'])])
    style.configure('TCheckbutton', background=c['background'], indicatorbackground='white')
    style.map('TCheckbutton', background=[('active', '#FBE5E8')])
    style.configure('TNotebook', background=c['background'], borderwidth=0)
    style.configure('TNotebook.Tab', background='#F4E1E4', padding=(18, 8))
    # clam標準のselected余白が基本設定を上書きするため、両状態を明示する。
    style.map('TNotebook.Tab', padding=[('selected', (18, 10, 18, 8)), ('!selected', (18, 4, 18, 4))],
              background=[('selected', '#F2C4CF')],
              foreground=[('selected', '#772C40')])
    style.configure('Treeview', background=c['white'], fieldbackground=c['white'],
                    foreground=c['text'], rowheight=26, bordercolor='#EBD0D5')
    style.map('Treeview', background=[('selected', '#F2C4CF')], foreground=[('selected', '#652438')])
    style.configure('Treeview.Heading', background='#F9E4E8', foreground='#8F354B',
                    font=('Yu Gothic UI', 10, 'bold'), padding=(8, 7))
    style.map('Treeview.Heading', background=[('active', '#F5D4DD')])
    style.configure('Vertical.TScrollbar', background='#F0C9D1', troughcolor='#FFF6F4', arrowcolor='#995365')

