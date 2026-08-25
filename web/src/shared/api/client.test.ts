// HTTP 客户端契约测试：验证成功响应反序列化以及领域化错误转换。
import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./client";

afterEach(() => {
  // 每个用例恢复全局 fetch，避免模拟状态泄漏到后续测试。
  vi.unstubAllGlobals();
});

describe("requestJson", () => {
  it("返回成功响应中的 JSON 数据", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestJson<{ status: string }>("/healthz")).resolves.toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/healthz",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
  });

  it("把失败响应转换为包含状态码的 ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "审批已过期" }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const request = requestJson("/api/v1/plans/expired/approve");
    await expect(request).rejects.toMatchObject({ message: "审批已过期", status: 409 });
  });
});
