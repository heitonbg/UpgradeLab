"""HTTPS destination policy. Syntax validation alone never authorizes a socket."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
import ipaddress
import re
import socket
from threading import BoundedSemaphore
from urllib.parse import quote, urlsplit, urlunsplit
from app.services.search_time import remaining

class NetworkPolicyError(RuntimeError):
    pass


class NetworkTransportError(NetworkPolicyError):
    def __init__(self,outcome,message):
        super().__init__(message)
        self.outcome=outcome

@dataclass(frozen=True)
class Target:
    url: str
    host: str
    path: str
    port: int = 443

@dataclass(frozen=True)
class Address:
    family: int
    ip: str

# Explicit exclusions also cover older Python ipaddress classifications and
# transition/NAT64 prefixes that can translate an apparently global IPv6 to IPv4.
V4_DENY=tuple(map(ipaddress.ip_network,(
    '0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16',
    '172.16.0.0/12','192.0.0.0/24','192.0.2.0/24','192.88.99.0/24','192.168.0.0/16',
    '198.18.0.0/15','198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4')))
V6_DENY=tuple(map(ipaddress.ip_network,('64:ff9b::/96','64:ff9b:1::/48','2001::/32','2002::/16')))
_dns_pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix='public-dns')
_dns_slots=BoundedSemaphore(4)

def public_address(value):
    try:
        address=ipaddress.ip_address(value)
        if isinstance(address,ipaddress.IPv6Address) and address.ipv4_mapped:
            address=address.ipv4_mapped
        denied=V4_DENY if address.version==4 else V6_DENY
        if (not address.is_global or address.is_multicast or address.is_reserved or
                address.is_unspecified or any(address in network for network in denied)):
            raise ValueError()
        return address
    except ValueError:
        raise NetworkPolicyError('Сетевое назначение не является допустимым публичным адресом') from None

def normalized_host(value):
    if not value or '%' in value or '\\' in value:
        raise NetworkPolicyError('Некорректное имя сетевого назначения')
    try:
        return str(public_address(value))
    except NetworkPolicyError:
        try:
            ipaddress.ip_address(value)
        except ValueError:
            pass
        else:
            raise
    try:
        host=value[:-1] if value.endswith('.') else value
        host=host.encode('idna').decode('ascii').lower()
    except (UnicodeError,ValueError):
        raise NetworkPolicyError('Некорректное имя сетевого назначения') from None
    if (len(host)>253 or '.' not in host or host.endswith(('.localhost','.local','.internal','.lan','.home','.arpa','.invalid','.test')) or
            any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) for label in host.split('.'))):
        raise NetworkPolicyError('Локальное или некорректное DNS-имя запрещено')
    return host

@dataclass(frozen=True)
class Policy:
    domains: tuple = ()
    hosts: tuple = ()

    def permits(self,host):
        return (not self.domains and not self.hosts or host in self.hosts or
                any(host==domain or host.endswith('.'+domain) for domain in self.domains))

def validate_url(url,policy=Policy()):
    if not isinstance(url,str) or len(url)>4096 or any(ord(char)<=32 or ord(char)==127 for char in url) or '\\' in url:
        raise NetworkPolicyError('Неоднозначный или некорректный URL')
    try:
        parsed=urlsplit(url)
        if (parsed.scheme!='https' or parsed.username is not None or parsed.password is not None or
                '@' in parsed.netloc or parsed.port not in (None,443)):
            raise ValueError()
        host=normalized_host(parsed.hostname)
        if not policy.permits(host):
            raise NetworkPolicyError('Адрес находится за пределами разрешённого источника')
        if re.search(r'%(?![0-9a-fA-F]{2})',parsed.path+'?'+parsed.query):
            raise ValueError()
        authority='['+host+']' if ':' in host else host
        path=quote(parsed.path or '/',safe="/%:@!$&'()*+,;=-._~")
        query=quote(parsed.query,safe="/?%:@!$&'()*+,;=-._~")
        return Target(urlunsplit(('https',authority,path,query,'')),host,path+('?' + query if query else ''))
    except (ValueError,UnicodeError):
        raise NetworkPolicyError('Нужен корректный HTTPS URL без авторизации и нестандартного порта') from None

def resolve_public(target,deadline):
    try:
        literal=ipaddress.ip_address(target.host)
    except ValueError:
        literal=None
    if literal is not None:
        address=public_address(str(literal))
        return (Address(socket.AF_INET if address.version==4 else socket.AF_INET6,str(address)),)
    if not _dns_slots.acquire(timeout=remaining(deadline,3)):
        raise TimeoutError('DNS-проверка временно занята')
    def lookup():
        try:
            return socket.getaddrinfo(target.host,target.port,socket.AF_UNSPEC,socket.SOCK_STREAM)
        finally:
            _dns_slots.release()
    try:
        future=_dns_pool.submit(lookup)
    except Exception:
        _dns_slots.release()
        raise
    try:
        records=future.result(timeout=remaining(deadline,3))
    except FutureTimeout:
        # A running resolver cannot be killed safely. It retains one of four
        # slots until completion; timed-out callers never start a connection.
        raise TimeoutError('DNS-проверка превысила лимит времени') from None
    except OSError:
        raise NetworkTransportError('dns_error','Не удалось определить публичный адрес источника') from None
    addresses=[]
    for family,_,_,_,sockaddr in records:
        if family not in (socket.AF_INET,socket.AF_INET6):
            raise NetworkPolicyError('Неизвестное семейство DNS-адреса')
        address=public_address(sockaddr[0])
        item=Address(socket.AF_INET if address.version==4 else socket.AF_INET6,str(address))
        if item not in addresses:
            addresses.append(item)
    if not addresses:
        raise NetworkPolicyError('DNS не вернул допустимых адресов')
    return tuple(addresses)
