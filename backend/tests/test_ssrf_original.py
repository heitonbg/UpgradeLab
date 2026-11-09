"""No real network: SSRF regressions mock DNS, transport and browser."""
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.store_providers import fetch
from app.services.browser_offers import browser_context
from app.core.config import settings

def answer(ip):
    family=socket.AF_INET6 if ':' in ip else socket.AF_INET
    return (family,socket.SOCK_STREAM,6,'',(ip,443,0,0) if family==socket.AF_INET6 else (ip,443))

class OriginalSSRFTests(unittest.TestCase):
    def setUp(self):
        response=Mock(status_code=200,encoding='utf-8',headers={})
        response.iter_content.return_value=[b'<html>fixture</html>']
        response.__enter__=Mock(return_value=response)
        response.__exit__=Mock(return_value=False)
        self.session=patch('requests.Session').start()
        self.addCleanup(patch.stopall)
        self.session.return_value.__enter__.return_value.get.return_value=response
        self.socket=patch('socket.socket',side_effect=AssertionError('No actual socket is allowed')).start()

    def test_private_dns_destination_is_rejected_before_connection(self):
        with patch('socket.getaddrinfo',return_value=[answer('10.0.0.1')]):
            with self.assertRaises(RuntimeError):
                fetch('https://www.regard.ru/product/1/fixture',store='regard')

    def test_mixed_public_and_private_dns_answers_are_rejected(self):
        with patch('socket.getaddrinfo',return_value=[answer('93.184.216.34'),answer('::1')]):
            with self.assertRaises(RuntimeError):
                fetch('https://www.regard.ru/product/1/fixture',store='regard')

    def test_initial_store_host_is_validated_not_only_redirect(self):
        with self.assertRaises(RuntimeError):
            fetch('https://unrelated.example/product/1/fixture',store='regard')

    def test_initial_non_https_scheme_is_rejected(self):
        with self.assertRaises(RuntimeError):
            fetch('http://www.regard.ru/product/1/fixture',store='regard')

    def test_initial_nonstandard_port_is_rejected(self):
        with self.assertRaises(RuntimeError):
            fetch('https://www.regard.ru:8443/product/1/fixture',store='regard')

    def test_browser_with_no_verified_network_isolation_does_not_start(self):
        playwright=Mock()
        playwright.chromium.executable_path='C:/fixture/chrome.exe'
        api=MagicMock()
        api.sync_playwright.return_value.__enter__.return_value=playwright
        with patch.dict(sys.modules,{'playwright':Mock(),'playwright.sync_api':api}),patch.object(
                settings,'offers_browser_enabled',True):
            with self.assertRaises(RuntimeError):
                with browser_context():
                    pass

if __name__=='__main__': unittest.main()
