"""app.py分割（2026-10-21、a24cb34）の旧新比較。引数：旧リポジトリ、新リポジトリ

1. 旧Appの全メソッドとクラス属性が、新App＋HistoryActions/ManualActions/SampleActionsの
   どこか1か所に、構文木で同一のまま存在するか。
2. 各メソッドが参照するモジュールの名前（messagebox、Image、manual_review等）が、
   旧版と同じオブジェクト（辞書は同値）を指すか。
"""
import ast, importlib.util, sys
old_repo, new_repo = sys.argv[1], sys.argv[2]
CLASSES = {'drop_tool/app.py': 'App', 'drop_tool/history_actions.py': 'HistoryActions',
           'drop_tool/manual_actions.py': 'ManualActions', 'drop_tool/sample_actions.py': 'SampleActions'}


def members(path, name):
    tree = ast.parse(open(path, encoding='utf-8').read())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    funcs = {f.name: ast.dump(f) for f in cls.body if isinstance(f, ast.FunctionDef)}
    attrs = [ast.dump(x) for x in cls.body if not isinstance(x, ast.FunctionDef)
             and not (isinstance(x, ast.Expr) and isinstance(x.value, ast.Constant))]
    return funcs, attrs


old_funcs, old_attrs = members(f'{old_repo}/drop_tool/app.py', 'App')
new_funcs = {}
for rel, name in CLASSES.items():
    funcs, attrs = members(f'{new_repo}/{rel}', name)
    assert not set(funcs) & set(new_funcs), set(funcs) & set(new_funcs)
    new_funcs.update(funcs)
    if name == 'App':
        print('App class attributes same:', attrs == old_attrs)
    else:
        print(f'{name} class attributes:', attrs or 'none')
print('methods old/new:', len(old_funcs), len(new_funcs), 'same names:', set(old_funcs) == set(new_funcs))
print('methods differing:', [k for k in old_funcs if old_funcs[k] != new_funcs.get(k)])

# 2. 参照先の同一性（旧app.pyを別名で読み込み、新Appと同じプロセスで比べる）
sys.path[:0] = [new_repo, new_repo + '/tests']
import _headless; _headless.install()
spec = importlib.util.spec_from_file_location('drop_tool._app_before', f'{old_repo}/drop_tool/app.py')
old = importlib.util.module_from_spec(spec); sys.modules[spec.name] = old; spec.loader.exec_module(old)
from drop_tool.app import App


def names(code):
    found = set(code.co_names)
    for const in code.co_consts:
        if hasattr(const, 'co_names'):
            found |= names(const)
    return found


bad = []
for name, fn in vars(old.App).items():
    if not hasattr(fn, '__code__'):
        continue
    new_globals = getattr(App, name).__globals__
    for n in names(fn.__code__):
        if n in old.__dict__:
            a, b = old.__dict__[n], new_globals.get(n, '<missing>')
            if not (a is b or (isinstance(a, dict) and a == b)):
                bad.append((name, n))
print('global name mismatches:', bad)
