"""提取公网实验限流所需的访客身份。

默认不信任任何代理头。只有部署明确保证入口覆盖 X-Real-IP、且 Caddy 不直接对公网开放时，
组合根才会启用该头；这里始终不读取可任意拼接的 X-Forwarded-For 首项。
"""

from ipaddress import ip_address

from fastapi import Request


def visitor_identity(request: Request, trust_real_ip_header: bool = False) -> str:
    """按部署信任边界返回访客 IP；默认只使用不可伪造的直接对端。"""

    candidate = request.headers.get("X-Real-IP", "").strip()
    if trust_real_ip_header and candidate:
        try:
            return str(ip_address(candidate))
        except ValueError:
            # 非法代理头不参与限流键，回退到无法由请求头伪造的连接地址。
            pass
    return request.client.host if request.client else "unknown"
