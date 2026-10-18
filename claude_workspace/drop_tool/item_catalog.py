"""正式名の辞書と利用者の集計設定。過去の観測行は設定変更で書き換えない。"""
import copy
import difflib
import json
from .tracker import ROOT, Rules, normalize
from .item_links import name_key, resolve_name

KINDS = {'material': '集計', 'excluded': '除外', 'review': '未確認'}


def lookup_key(name):
    """数量だけを除いて照合する。性別やスクロールの接尾辞は別名として保持。"""
    return name_key(name)


class ItemCatalog:
    """配布辞書は読み取り専用。追加名・扱いは利用者のrecords.jsonに保存する。"""
    def __init__(self, store):
        self.store = store
        master = json.loads((ROOT / 'item-master.json').read_text('utf-8'))
        if master.get('schema_version') != 1:
            raise ValueError('アイテム辞書の形式に対応していません。')
        self.entries = {lookup_key(x['name']): dict(x) for x in master['items']}
        self.rules = Rules(store.data['overrides'])
        # 旧版で覚えた名前と手動JSONの正式名も、再登録せず管理できる。
        legacy = (list(store.data['overrides']) + store.data.get('item_names', [])
                  + list(store.data.get('item_links', {})) + list(store.data.get('item_links', {}).values())
                  + [x['name'] for x in store.data['templates']]
                  + self.rules.rules['exclude_exact'] + self.rules.rules['confirmed_materials'])
        for name in legacy:
            key = lookup_key(name)
            self.entries.setdefault(key, {'name': name, 'category': 'user'})
        self.aliases = {lookup_key(alias): key for key, item in self.entries.items()
                        for alias in item.get('aliases', [])}

    def find(self, name):
        key = lookup_key(name)
        return self.entries.get(self.aliases.get(key, key))

    def classify(self, name):
        name = resolve_name(self.store.data, name)
        item = self.find(name)
        canonical = item['name'] if item else name
        overrides = self.store.data['overrides']
        # 数量付きで旧版が学習した指定も優先。新しい基本名指定は全数量に適用。
        for candidate in (name, canonical):
            if normalize(candidate) in overrides:
                return overrides[normalize(candidate)]
        previous = self.rules.classify(canonical)
        if previous != 'review':
            return previous
        # 辞書登録と集計許可を分離。未指定の品は利用者が一括選択できる。
        return 'review'

    def candidates(self, name):
        """近い正式名は提案だけに留める。潰れた文字を推測して確定しない。"""
        if not name or name == '読取不明' or self.find(name):
            return []
        keys = difflib.get_close_matches(lookup_key(name), self.entries, n=3, cutoff=.65)
        return [self.entries[key]['name'] for key in keys]

    def search(self, query):
        """部分一致を先に表示し、類似名を後ろへ並べる。選択は利用者が行う。"""
        query = lookup_key(query)
        items = {key:item for key,item in self.entries.items()
                 if key not in self.store.data.get('item_links', {})}
        direct = sorted(key for key in items if query in key)
        similar = difflib.get_close_matches(query, items, n=12, cutoff=.55) if query else []
        return [items[key]['name'] for key in dict.fromkeys(direct + similar)]

    def set_policy(self, names, kind):
        """一括更新を1回で保存。保存エラー時はメモリーも戻す。履歴には触れない。"""
        if kind not in KINDS:
            raise ValueError('集計・除外・未確認から選んでください。')
        names = [normalize(n) for n in names]
        if not names or any(not n or len(n) > 160 or n == '読取不明' for n in names):
            raise ValueError('正式な品名を入力・選択してください。')
        previous = copy.deepcopy(self.store.data)
        try:
            registered = self.store.data.setdefault('item_names', [])
            for name in names:
                name = resolve_name(self.store.data, name)
                item = self.find(name)
                name = normalize(item['name']) if item else name
                if name not in registered:
                    registered.append(name)
                # 基本名変更で、過去の数量付き指定だけ残って矛盾するのを防ぐ。
                for old in list(self.store.data['overrides']):
                    if lookup_key(old) == lookup_key(name):
                        self.store.data['overrides'][old] = kind
                self.store.data['overrides'][name] = kind
            self.store.save()
        except Exception:
            self.store.data = previous
            raise
        self.__init__(self.store)

    def apply_pending(self, run_id):
        """明示操作の対象周回だけに設定を反映。確定済み周回の再集計はしない。"""
        run = self.store.find(run_id)
        if run['status'] != 'review':
            raise ValueError('確認待ちの周回を選んでください。確定済みの記録は変更しません。')
        previous = copy.deepcopy(run['rows'])
        for row in run['rows']:
            if lookup_key(row['name']) in self.store.data.get('item_links', {}) or row.get('resolved_name'):
                continue  # 対応付けた原名は残し、表示・確定・集計時に解決する。
            item = self.find(row['name'])
            if item:
                row['name'] = item['name']
                row['kind'] = self.classify(item['name'])
                if 'reviewed_kind' in row:
                    row['reviewed_kind'] = row['kind']
        try:
            self.store.save()
        except Exception:
            run['rows'] = previous
            raise
