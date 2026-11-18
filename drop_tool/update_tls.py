"""更新通信の証明書検証。OSの信頼設定にMozillaの公開CAを補完する。"""
import ssl
import certifi


def create_context():
    """ホスト名・証明書検証とランタイムの拒否設定を維持し、公開CAを加える。"""
    context = ssl.create_default_context()
    # PCの証明書一覧だけでは発行元が不足する場合がある。検証は無効化しない。
    context.load_verify_locations(cafile=certifi.where())
    return context
