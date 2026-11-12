"""Pinned HTTPS transport: no proxy environment, no second hostname resolution."""
import codecs
from dataclasses import dataclass
from email.message import Message
from functools import lru_cache
import http.client
import json
import socket
import ssl
from threading import BoundedSemaphore, Event, Timer
import time
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request
import zlib
import requests
from requests.cookies import RequestsCookieJar
from requests.structures import CaseInsensitiveDict
from app.services.network_policy import NetworkPolicyError, NetworkTransportError, Policy, public_address, resolve_public, validate_url
from app.services.search_time import remaining

MAX_BYTES=8*1024*1024
MAX_REDIRECTS=3
_http_slots=BoundedSemaphore(4)

@lru_cache(maxsize=1)
def tls_context():
    context=ssl.create_default_context(cafile=requests.certs.where())
    context.set_alpn_protocols(['http/1.1'])
    return context

class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self,target,addresses,deadline):
        super().__init__(target.host,443,timeout=remaining(deadline,3),context=tls_context())
        self.addresses=addresses
        self.deadline=deadline
        self.live_socket=None

    def connect(self):
        last=None
        for address in self.addresses:
            raw=None
            try:
                # socket.connect uses a checked numeric address, never the
                # logical hostname and never socket.create_connection/getaddrinfo.
                raw=socket.socket(address.family,socket.SOCK_STREAM)
                self.live_socket=raw
                raw.settimeout(remaining(self.deadline,3))
                raw.connect((address.ip,443) if address.family==socket.AF_INET else (address.ip,443,0,0))
                if public_address(raw.getpeername()[0]) != public_address(address.ip):
                    raise NetworkPolicyError('Адрес соединения отличается от проверенного DNS-назначения')
                self.sock=self._context.wrap_socket(raw,server_hostname=self.host)
                self.live_socket=self.sock
                self.sock.settimeout(remaining(self.deadline,5))
                return
            except NetworkPolicyError:
                self.abort()
                raise
            except (OSError,ssl.SSLError) as error:
                self.abort()
                last=error
        raise last or NetworkPolicyError('Публичное соединение недоступно')

    def abort(self):
        live=self.live_socket
        if live is not None:
            try:live.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            live.close()
        self.close()

@dataclass
class SafeResponse:
    status_code: int
    headers: CaseInsensitiveDict
    content: bytes
    url: str

    @property
    def text(self):
        message=Message()
        message['content-type']=self.headers.get('Content-Type','')
        encoding=message.get_content_charset() or 'utf-8'
        try:codecs.lookup(encoding)
        except LookupError:encoding='utf-8'
        return self.content.decode(encoding,errors='replace')

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code>=400:
            response=requests.Response()
            response.status_code=self.status_code
            raise requests.HTTPError(f'HTTP {self.status_code}',response=response)

def read_body(response,connection,deadline,max_bytes,extra_media_types=(),sink=None):
    length=response.getheader('Content-Length')
    if length is not None:
        try:
            if not 0<=int(length)<=max_bytes:raise ValueError()
        except ValueError:
            raise NetworkPolicyError('Ответ источника слишком большой или имеет некорректный размер') from None
    media=(response.getheader('Content-Type') or '').split(';',1)[0].strip().lower()
    if media and media not in extra_media_types and not (media in ('text/html','text/plain','text/xml','text/javascript',
                      'application/xhtml+xml','application/json','application/xml','application/rss+xml') or
                      media.startswith('application/') and media.endswith(('+json','+xml'))):
        raise NetworkPolicyError('Источник вернул неподдерживаемый Content-Type')
    encoding=(response.getheader('Content-Encoding') or 'identity').strip().lower()
    if encoding not in ('identity','gzip','deflate'):
        raise NetworkPolicyError('Источник вернул неподдерживаемое сжатие')
    decoder=zlib.decompressobj(31 if encoding=='gzip' else zlib.MAX_WBITS) if encoding!='identity' else None
    body=bytearray()
    wire=0;decoded_size=0
    while True:
        timeout=remaining(deadline,5)
        if connection.live_socket is not None:
            connection.live_socket.settimeout(timeout)
        chunk=response.read1(65536)
        if not chunk:break
        wire+=len(chunk)
        if wire>max_bytes:
            raise NetworkPolicyError('Ответ источника слишком большой')
        try:
            decoded=decoder.decompress(chunk,max_bytes-decoded_size+1) if decoder else chunk
        except zlib.error:
            raise NetworkPolicyError('Некорректный сжатый ответ источника') from None
        if decoded_size+len(decoded)>max_bytes:
            raise NetworkPolicyError('Распакованный ответ источника слишком большой')
        decoded_size+=len(decoded)
        if sink is None:body.extend(decoded)
        else:sink.write(decoded)
    if decoder and (not decoder.eof or decoder.unused_data):
        raise NetworkPolicyError('Неполный или неоднозначный сжатый ответ')
    remaining(deadline,5)
    return bytes(body)

class SafeSession:
    """Small session interface for existing catalog scripts; every hop is pinned."""
    trust_env=False
    def __init__(self,policy=Policy(),*,extra_media_types=()):
        self.policy=policy
        self.extra_media_types=tuple(extra_media_types)
        self.headers={'User-Agent':'UpgradeLab/1.0','Accept-Language':'ru-RU'}
        self.cookies=RequestsCookieJar()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):pass  # Each response/socket is already closed before returning.
    def get(self,url,**kwargs):return self.request('GET',url,**kwargs)
    def post(self,url,**kwargs):return self.request('POST',url,**kwargs)
    def get_to(self,url,sink,**kwargs):return self.request('GET',url,_sink=sink,**kwargs)

    def request(self,method,url,*,params=None,data=None,headers=None,deadline=None,
                timeout=None,allow_redirects=True,max_bytes=MAX_BYTES,_sink=None):
        if method not in ('GET','POST'):
            raise NetworkPolicyError('Неподдерживаемый метод загрузки')
        deadline=min(deadline,time.monotonic()+30) if deadline is not None else time.monotonic()+30
        # Legacy caller timeout is an upper bound, not permission for an
        # unbounded read. Fine-grained connect/read caps are 3/5 seconds.
        if isinstance(timeout,(int,float)):
            deadline=min(deadline,time.monotonic()+max(0,timeout))
        elif isinstance(timeout,tuple):
            deadline=min(deadline,time.monotonic()+sum(timeout))
        if params:
            parsed=urlsplit(url)
            url=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,
                           parsed.query+('&' if parsed.query else '')+urlencode(params,doseq=True),parsed.fragment))
        target=validate_url(url,self.policy)
        # Unrestricted policy means one administrator-configured hostname,
        # never permission to redirect to arbitrary public origins.
        policy=self.policy if self.policy.domains or self.policy.hosts else Policy(hosts=(target.host,))
        outgoing=CaseInsensitiveDict(self.headers)
        outgoing.update(headers or {})
        if any(key.lower() in ('proxy-authorization','cookie') for key in outgoing):
            raise NetworkPolicyError('Недопустимые заголовки загрузки')
        outgoing['Accept-Encoding']='gzip, deflate'
        outgoing['Connection']='close'
        payload=urlencode(data,doseq=True).encode('ascii') if isinstance(data,dict) else data
        if payload is not None and 'Content-Type' not in outgoing:
            outgoing['Content-Type']='application/x-www-form-urlencoded'
        if not _http_slots.acquire(timeout=remaining(deadline,5)):
            raise TimeoutError('Сетевые загрузки временно заняты')
        try:
            for hop in range(MAX_REDIRECTS+1):
                target=validate_url(target.url,policy)
                addresses=resolve_public(target,deadline)
                response=self._once(method,target,addresses,outgoing,payload,deadline,max_bytes,**({'sink':_sink} if _sink is not None else {}))
                if response.status_code not in (301,302,303,307,308):
                    return response
                if not allow_redirects or 'Authorization' in outgoing:
                    raise NetworkPolicyError('Перенаправление авторизованного источника запрещено')
                if hop==MAX_REDIRECTS:
                    raise NetworkPolicyError('Слишком много перенаправлений источника')
                location=response.headers.get('Location')
                if not location:
                    raise NetworkPolicyError('Перенаправление без допустимого адреса')
                target=validate_url(urljoin(target.url,location),policy)
                if response.status_code==303 or response.status_code in (301,302) and method=='POST':
                    method,payload='GET',None
                    outgoing.pop('Content-Type',None)
        finally:
            _http_slots.release()

    def _once(self,method,target,addresses,headers,payload,deadline,max_bytes,sink=None):
        connection=PinnedHTTPSConnection(target,addresses,deadline)
        expired=Event()
        def abort():
            expired.set()
            connection.abort()
        timer=Timer(remaining(deadline,30),abort)
        timer.daemon=True
        response=None
        try:
            timer.start()
            if expired.is_set():
                raise TimeoutError('Истёк срок загрузки')
            remaining(deadline,5)
            request=Request(target.url)
            self.cookies.add_cookie_header(request)
            outgoing=CaseInsensitiveDict(headers)
            outgoing['Host']='['+target.host+']' if ':' in target.host else target.host
            if request.has_header('Cookie'):
                outgoing['Cookie']=request.get_header('Cookie')
            connection.request(method,target.path,body=payload,headers=dict(outgoing))
            response=connection.getresponse()
            self.cookies.extract_cookies(response,request)
            body=read_body(response,connection,deadline,max_bytes,self.extra_media_types,sink if response.status==200 else None)
            if expired.is_set():
                raise TimeoutError('Истёк срок загрузки')
            return SafeResponse(response.status,CaseInsensitiveDict(response.getheaders()),body,target.url)
        except (socket.timeout,TimeoutError):
            raise TimeoutError('Источник не ответил за отведённое время') from None
        except ssl.SSLCertVerificationError:
            raise NetworkTransportError('certificate_error','Сертификат HTTPS источника не прошёл проверку') from None
        except ssl.SSLError:
            raise NetworkTransportError('tls_error','Не удалось согласовать защищённое TLS-соединение') from None
        except ConnectionError:
            raise NetworkTransportError('connection_error','Соединение с источником прервано или отклонено') from None
        except http.client.HTTPException:
            raise NetworkTransportError('http_protocol_error','Некорректный ответ протокола HTTP') from None
        except OSError:
            if expired.is_set():
                raise TimeoutError('Источник превысил общее время загрузки') from None
            raise NetworkTransportError('network_error','Не удалось установить проверенное HTTPS-соединение') from None
        finally:
            timer.cancel()
            if response is not None:response.close()
            connection.abort()
