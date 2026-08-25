// Hash 路由无需服务器重写规则，适合 SSH 端口转发和未来恢复 /aiops/ 子路径部署。
import { useEffect, useState } from "react";

function currentPath(): string {
  return window.location.hash.replace(/^#/, "") || "/overview";
}

export function useHashRoute(): string {
  const [path, setPath] = useState(currentPath);

  useEffect(() => {
    const handleChange = () => setPath(currentPath());
    window.addEventListener("hashchange", handleChange);
    return () => window.removeEventListener("hashchange", handleChange);
  }, []);

  return path;
}
