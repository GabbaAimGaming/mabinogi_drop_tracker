"""ローカルTLSで検証を維持し、取得経路が補完CAを使うことを確認する。"""
from pathlib import Path
import socket
import ssl
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from drop_tool import update_tls, updater

FIXTURES = Path(__file__).parent / 'tls-fixtures'


class UpdateTLSTests(unittest.TestCase):
    def test_context_requires_peer_verification_and_hostname(self):
        context = update_tls.create_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()['x509_ca'], 0)

    def test_public_roots_are_available_when_machine_store_is_empty(self):
        empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.assertLessEqual(empty.cert_store_stats()['x509_ca'], 1)  # ランタイムの拒否CAが1件ある場合は保持。
        with patch.object(update_tls.ssl, 'create_default_context', return_value=empty):
            context = update_tls.create_context()
        self.assertGreater(context.cert_store_stats()['x509_ca'], 80)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_missing_ca_bundle_fails_closed(self):
        with patch.object(update_tls.certifi, 'where', return_value='missing-ca-bundle.pem'):
            with self.assertRaises(FileNotFoundError):
                update_tls.create_context()

    def local_handshake(self, trust_local, hostname):
        server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server.load_cert_chain(str(FIXTURES / 'localhost-cert.pem'), str(FIXTURES / 'localhost-key.pem'))
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(5)
        port = listener.getsockname()[1]
        errors = []
        def serve():
            try:
                peer, _ = listener.accept()
                with peer:
                    try:
                        with server.wrap_socket(peer, server_side=True) as tls:
                            tls.sendall(b'OK')
                    except ssl.SSLError:
                        pass  # 拒否されたクライアントからのTLSアラートは想定内。
            except Exception as exc:
                errors.append(exc)
            finally:
                listener.close()
        worker = threading.Thread(target=serve, daemon=True);worker.start()
        context = update_tls.create_context()
        if trust_local:
            context.load_verify_locations(cafile=str(FIXTURES / 'localhost-cert.pem'))
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=5) as raw:
                with context.wrap_socket(raw, server_hostname=hostname) as tls:
                    self.assertEqual(tls.recv(2), b'OK')
        finally:
            worker.join(6)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])

    def test_trusted_local_certificate_connects(self):
        self.local_handshake(True, 'localhost')

    def test_untrusted_certificate_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.local_handshake(False, 'localhost')

    def test_hostname_mismatch_is_rejected_even_with_trusted_certificate(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.local_handshake(True, 'wrong.invalid')

    def test_download_and_old_list_both_use_verified_context(self):
        # ネットワークはモック。実際のHTTPSHandlerへ渡された検証条件を確認する。
        context = update_tls.create_context()
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(updater, 'create_context', return_value=context) as create, \
                patch.object(updater, 'build_opener') as build:
            build.return_value.open.side_effect = RuntimeError('network suppressed')
            for operation in (lambda: updater.download(updater.DEFAULT_SOURCE, Path(folder)/'feed', 100), updater.old_releases):
                with self.assertRaises(RuntimeError): operation()
            self.assertEqual(create.call_count, 2)
            for call in build.call_args_list:
                handler = next(x for x in call.args if isinstance(x, updater.HTTPSHandler))
                self.assertIs(handler._context, context)
                self.assertTrue(handler._context.check_hostname)
                self.assertEqual(handler._context.verify_mode, ssl.CERT_REQUIRED)
