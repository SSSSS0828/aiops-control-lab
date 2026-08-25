// 通用只读资源 Hook 统一处理加载、刷新和错误状态，不隐藏业务写操作。
import { useCallback, useEffect, useState } from "react";

export interface ApiResource<T> {
  data: T | undefined;
  error: string | undefined;
  loading: boolean;
  refresh: () => Promise<void>;
}

export function useApiResource<T>(loader: () => Promise<T>): ApiResource<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      setData(await loader());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    // 把首次请求放入微任务，Effect 本身只负责建立异步同步关系，不同步触发级联渲染。
    void Promise.resolve().then(refresh);
  }, [refresh]);

  return { data, error, loading, refresh };
}
