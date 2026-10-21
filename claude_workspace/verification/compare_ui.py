"""ui.build_widgetsの分割（2026-10-21、a24cb34）の旧新比較。引数：旧リポジトリ、新リポジトリ

tk/ttkと画面部品（ScrollablePane、KarenBanner、CsvViews、ItemViews、SettingsViews）を
「呼ばれた順に名前と引数を記録するだけ」の代役に差し替え、旧新のbuild_widgetsを実行する。
部品を作る呼び出しの並び・引数と、Appへ代入された属性が一致すれば、画面構成は同じ。
"""
import importlib.util, sys, types
old_repo, new_repo = sys.argv[1], sys.argv[2]
sys.path[:0] = [new_repo, new_repo + '/tests']
import _headless; _headless.install()
import drop_tool.item_views as item_views, drop_tool.settings_views as settings_views


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def run(module):
    log = []

    class Obj:
        def __init__(self, name): self._n = name
        def __getattr__(self, a):
            if a.startswith('__'): raise AttributeError(a)
            return Call(f'{self._n}.{a}')
        def __getitem__(self, k): return Obj(f'{self._n}[{k!r}]')
        def __repr__(self): return self._n

    class Call:
        def __init__(self, name): self.name = name
        def __call__(self, *a, **k):
            result = Obj(f'#{len(log)}')
            log.append((self.name, [fmt(x) for x in a], {kk: fmt(v) for kk, v in sorted(k.items())}, result._n))
            return result
        def __getattr__(self, a): return Call(f'{self.name}.{a}')

    class Bound:
        def __init__(self, n): self.n = n
        def __call__(self, *a, **k): log.append(('app.' + self.n, [fmt(x) for x in a], {}, ''))
        def __repr__(self): return 'app.' + self.n

    def fmt(x):
        if isinstance(x, Call): return x.name
        if callable(x) and getattr(x, '__name__', '') == '<lambda>': return '<lambda>'
        return repr(x)

    class App:
        def __init__(self):
            self.root = Obj('root'); self.store = types.SimpleNamespace(folder='F')
            for v in ('player_name', 'status', 'diagnostic', 'sound_enabled', 'summary'):
                setattr(self, v, Obj('var:' + v))
        def __getattr__(self, a): return Bound(a)
        def __repr__(self): return 'app'

    module.tk = Obj('tk'); module.ttk = Obj('ttk')
    module.KarenBanner = Call('KarenBanner'); module.ScrollablePane = Call('ScrollablePane'); module.CsvViews = Call('CsvViews')
    saved = item_views.ItemViews, settings_views.SettingsViews
    item_views.ItemViews, settings_views.SettingsViews = Call('ItemViews'), Call('SettingsViews')
    try:
        app = App(); module.build_widgets(app)
    finally:
        item_views.ItemViews, settings_views.SettingsViews = saved
    return log, {k: repr(v) for k, v in sorted(vars(app).items())}


old = run(load(f'{old_repo}/drop_tool/ui.py', 'drop_tool._ui_before'))
new = run(load(f'{new_repo}/drop_tool/ui.py', 'drop_tool._ui_after'))
print('calls old/new:', len(old[0]), len(new[0]), 'same calls:', old[0] == new[0], 'same app attributes:', old[1] == new[1])
