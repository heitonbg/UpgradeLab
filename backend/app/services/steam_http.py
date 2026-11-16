"""One pooled async HTTPX client; fixed Steam endpoints and pinned public DNS."""
from __future__ import annotations
import asyncio,json,time
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
import httpx,httpcore
from httpcore._backends.anyio import AnyIOBackend
from app.services.network_policy import Policy,validate_url,resolve_public,public_address,NetworkPolicyError
from app.core.config import settings

HOST="store.steampowered.com"
MAX_BYTES=2*1024*1024

def app_id(value):
    if isinstance(value,bool) or not str(value).isascii() or not str(value).isdigit() or not 0<int(value)<2147483647:
        raise ValueError("invalid_steam_app_id")
    return int(value)

class SteamFailure(Exception):
    def __init__(self,code,retry_after=0,transient=False):
        super().__init__(code);self.code=code;self.retry_after=retry_after;self.transient=transient

def retry_after(value,now=None):
    now=now or datetime.now(timezone.utc)
    try:
        if str(value).isdigit():return max(0,int(value))
        stamp=parsedate_to_datetime(str(value))
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        return max(0,int((stamp-now).total_seconds()))
    except (ValueError,TypeError,OverflowError):return 0

class PinnedBackend(AnyIOBackend):
    async def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        if isinstance(host,bytes):host=host.decode('ascii')
        target=validate_url('https://'+host,Policy(hosts=(HOST,)))
        if port!=443 or host!=HOST:raise NetworkPolicyError('steam_destination_denied')
        addresses=await asyncio.to_thread(resolve_public,target,time.monotonic()+5)
        last=None
        for address in addresses:
            try:
                stream=await super().connect_tcp(address.ip,port,timeout,local_address,socket_options)
                peer=stream.get_extra_info('server_addr')
                if not peer or public_address(peer[0])!=public_address(address.ip):
                    await stream.aclose();raise NetworkPolicyError('steam_peer_mismatch')
                return stream
            except (OSError,httpcore.NetworkError) as exc:last=exc
        raise last or NetworkPolicyError('steam_no_public_address')

class Stream(httpx.AsyncByteStream):
    def __init__(self,stream):self.stream=stream
    async def __aiter__(self):
        async for chunk in self.stream:yield chunk
    async def aclose(self):await self.stream.aclose()

class SteamTransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.pool=httpcore.AsyncConnectionPool(network_backend=PinnedBackend(),max_connections=1,
            max_keepalive_connections=1,keepalive_expiry=30,retries=0)
    async def handle_async_request(self,request):
        validate_url(str(request.url),Policy(hosts=(HOST,)))
        response=await self.pool.handle_async_request(httpcore.Request(method=request.method,
            url=httpcore.URL(scheme=request.url.raw_scheme,host=request.url.raw_host,
                             port=request.url.port,target=request.url.raw_path),
            headers=request.headers.raw,content=request.stream,extensions=request.extensions))
        return httpx.Response(response.status,headers=response.headers,stream=Stream(response.stream),extensions=response.extensions)
    async def aclose(self):await self.pool.aclose()

class SteamClient:
    def __init__(self,transport=None,before_request=None):
        self.before_request=before_request
        self.client=httpx.AsyncClient(transport=transport or SteamTransport(),trust_env=False,follow_redirects=False,
            timeout=httpx.Timeout(settings.steam_request_timeout_seconds,connect=5),
            headers={'User-Agent':'UpgradeLab/1.0','Accept':'application/json','Accept-Encoding':'identity'},
            limits=httpx.Limits(max_connections=1,max_keepalive_connections=1))
        self.lock=asyncio.Lock();self.requests=0
    async def __aenter__(self):return self
    async def __aexit__(self,*args):await self.client.aclose()
    async def _get(self,path,params):
        if path not in ('/api/appdetails','/api/storesearch/'):
            raise SteamFailure('endpoint_denied')
        async with self.lock:
            if self.before_request:await self.before_request()
            self.requests+=1
            try:
                async with asyncio.timeout(settings.steam_request_timeout_seconds):
                    async with self.client.stream('GET','https://'+HOST+path,params=params) as response:
                        if response.status_code!=200:
                            status=response.status_code
                            raise SteamFailure('http_'+str(status),retry_after(response.headers.get('Retry-After')),
                                               transient=status==429 or status>=500)
                        media=response.headers.get('Content-Type','').split(';')[0].strip().lower()
                        if media not in ('application/json','text/json'):
                            raise SteamFailure('invalid_content_type',transient=True)
                        if response.headers.get('Content-Encoding','identity').casefold() not in ('identity',''):
                            raise SteamFailure('unsupported_content_encoding')
                        length=response.headers.get('Content-Length')
                        if length and (not length.isdigit() or int(length)>MAX_BYTES):
                            raise SteamFailure('response_too_large')
                        content=bytearray()
                        async for part in response.aiter_bytes():
                            content.extend(part)
                            if len(content)>MAX_BYTES:raise SteamFailure('response_too_large')
                        try:data=json.loads(content)
                        except (ValueError,UnicodeError):raise SteamFailure('invalid_json',transient=True) from None
                        if not isinstance(data,dict):raise SteamFailure('invalid_json_shape',transient=True)
                        return data
            except SteamFailure:raise
            except (TimeoutError,httpx.TimeoutException,httpcore.TimeoutException):
                raise SteamFailure('timeout',transient=True) from None
            except (httpx.HTTPError,httpcore.NetworkError,OSError,NetworkPolicyError):
                raise SteamFailure('network_error',transient=True) from None
    async def details(self,appid):
        appid=app_id(appid)
        data=await self._get('/api/appdetails',{'appids':appid,'l':'english','cc':'us','filters':'basic,pc_requirements'})
        item=data.get(str(appid))
        if not isinstance(item,dict) or not item.get('success'):raise SteamFailure('app_not_found')
        result=item.get('data')
        if not isinstance(result,dict) or result.get('steam_appid')!=appid:raise SteamFailure('appid_mismatch')
        if result.get('type')!='game' or result.get('dlc_for_app') or result.get('demo_of_app'):
            raise SteamFailure('not_base_game')
        return result
    async def search(self,title):
        if not isinstance(title,str) or not 2<=len(title)<=200:raise SteamFailure('invalid_search_title')
        return await self._get('/api/storesearch/',{'term':title,'l':'english','cc':'us'})
