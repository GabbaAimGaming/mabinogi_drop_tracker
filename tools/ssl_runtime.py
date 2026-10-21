"""ビルド元のSSL実装が要求する証明書データを、実装と一緒に同梱する。"""
from pathlib import Path
import ssl


def runtime_data(module_file=None):
    """標準Pythonでは追加不要。実装固有の信頼設定は省略・無効化しない。"""
    module = Path(module_file or ssl.__file__)
    name = 'codex-rejected-cas.pem'
    if name not in module.read_text(encoding='utf-8'):
        return []
    certificate = module.with_name(name)
    if not certificate.is_file():
        raise FileNotFoundError('ビルド元のSSL実装に必要なファイルがありません：' + str(certificate))
    # 凍結後のssl.__file__と同じ内部ディレクトリへ配置する。
    return [(str(certificate), '.')]
