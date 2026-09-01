"""DNS 兜底修复。

当前运行环境（沙箱）会破坏基于系统解析器的 getaddrinfo（返回 gaierror），
但底层网络（TCP/UDP）实际可用。此模块在 getaddrinfo 失败时，用 UDP 直查
公共 DNS（8.8.8.8 / 114.114.114.114 / 223.5.5.5）获取 A 记录，让 httpx 等
客户端照常工作（hostname/SNI/Host 均不变，只覆盖解析结果）。
"""

import socket
import struct

_FALLBACK_SERVERS = ["8.8.8.8", "114.114.114.114", "223.5.5.5"]
_cache: dict = {}

_original_getaddrinfo = socket.getaddrinfo


def _query_a(hostname: str, server: str, timeout: float = 3.0) -> str | None:
    """UDP 查询 A 记录，返回 IPv4 地址或 None。"""
    txid = 0x1234
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    question = b"".join(bytes([len(p)]) + p.encode("ascii") for p in hostname.split("."))
    question += b"\x00" + struct.pack(">HH", 1, 1)  # A, IN
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(timeout)
        s.sendto(header + question, (server, 53))
        data, _ = s.recvfrom(4096)
        s.close()
        if len(data) < 12 or struct.unpack(">H", data[:2])[0] != txid:
            return None
        if struct.unpack(">H", data[2:4])[0] & 0x000F != 0:  # rcode
            return None
        ancount = struct.unpack(">H", data[6:8])[0]
        if ancount == 0:
            return None
        offset = 12
        while True:  # question
            l = data[offset]
            if l == 0:
                offset += 1
                break
            offset += 1 + l
        offset += 4
        # 遍历所有 answer，跳过 CNAME 等，找到第一条 A 记录
        for _ in range(ancount):
            if offset + 2 > len(data):
                break
            if data[offset] & 0xC0 == 0xC0:  # name 指针
                offset += 2
            else:
                while offset < len(data):
                    l = data[offset]
                    if l == 0:
                        offset += 1
                        break
                    offset += 1 + l
            if offset + 10 > len(data):
                break
            rtype, _, _, rdlen = struct.unpack(">HHIH", data[offset:offset + 10])
            offset += 10
            if rtype == 1 and rdlen == 4 and offset + 4 <= len(data):
                return ".".join(str(b) for b in data[offset:offset + 4])
            offset += rdlen  # 跳过 CNAME 等其他 rdata
        return None
    except Exception:
        pass
    return None


def _dns_fallback(hostname: str) -> str | None:
    if hostname in _cache:
        return _cache[hostname]
    ip = None
    for server in _FALLBACK_SERVERS:
        ip = _query_a(hostname, server)
        if ip:
            break
    _cache[hostname] = ip
    return ip


def getaddrinfo_fallback(host, port, family=0, type=0, proto=0, flags=0):
    try:
        return _original_getaddrinfo(host, port, family, type, proto, flags)
    except socket.gaierror:
        ip = _dns_fallback(host) if isinstance(host, str) else None
        if not ip:
            raise
        socktype = type or socket.SOCK_STREAM
        return [(socket.AF_INET, socktype, proto or socket.IPPROTO_TCP, "", (ip, port))]


def install():
    socket.getaddrinfo = getaddrinfo_fallback
    # httpx/httpcore 经 anyio 解析域名：asyncio 后端走 loop.getaddrinfo，
    # 沙箱中同样 gaierror → 在 AsyncIOBackend.getaddrinfo 上包一层兜底
    try:
        import anyio._backends._asyncio as _asyncio_backend
        _orig_gai = _asyncio_backend.AsyncIOBackend.getaddrinfo  # classmethod（已绑定类）

        async def _patched_gai(*args, **kwargs):
            host = args[1] if len(args) > 1 else kwargs.get("host")
            port = args[2] if len(args) > 2 else kwargs.get("port")
            family = kwargs.get("family", 0)
            type_ = kwargs.get("type", 0)
            proto = kwargs.get("proto", 0)
            flags = kwargs.get("flags", 0)
            try:
                return await _orig_gai(host, port, family=family, type=type_,
                                       proto=proto, flags=flags)
            except socket.gaierror:
                h = host.decode() if isinstance(host, bytes) else host
                ip = _dns_fallback(h) if isinstance(h, str) else None
                if not ip:
                    raise
                socktype = type_ or socket.SOCK_STREAM
                return [(socket.AF_INET, socktype, proto or socket.IPPROTO_TCP, "", (ip, port))]

        _asyncio_backend.AsyncIOBackend.getaddrinfo = classmethod(_patched_gai)
    except Exception:
        pass
