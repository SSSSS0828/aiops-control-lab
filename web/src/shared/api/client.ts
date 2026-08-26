// 统一 HTTP 客户端负责错误归一化，业务组件不直接处理响应协议细节。
export class ApiError extends Error {
  public constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

function resolveRequestPath(path: string): string {
  // Vite 会按部署参数写入 BASE_URL；根路径开发环境保持原 URL，不制造双斜线。
  const basePath = import.meta.env.BASE_URL.replace(/\/$/, "");
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${basePath}${normalizedPath}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(resolveRequestPath(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as {
      detail?: string;
      error?: string;
    };
    throw new ApiError(
      payload.detail ?? payload.error ?? `请求失败：${response.status}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}
