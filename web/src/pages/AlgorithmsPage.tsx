// 算法页如实展示在线、降级、离线实验和禁用状态。
import { useCallback } from "react";

import { listCapabilities } from "../shared/api/console";
import { PageHeader } from "../shared/components/PageHeader";
import { ErrorState, LoadingState } from "../shared/components/PageState";
import { useApiResource } from "../shared/hooks/useApiResource";

export function AlgorithmsPage() {
  const loader = useCallback(() => listCapabilities(), []);
  const { data = [], error, loading } = useApiResource(loader);
  if (loading && !data.length) return <LoadingState />;
  if (error && !data.length) return <ErrorState message={error} />;
  const groups = data.reduce<Record<string, typeof data>>((result, item) => {
    (result[item.category] ??= []).push(item);
    return result;
  }, {});
  return (
    <>
      <PageHeader
        description="能力存在不代表已进入在线数据流；本页明确展示每项技术的真实运行状态和使用边界。"
        eyebrow="ALGORITHM CATALOG"
        title="算法与 AI 能力"
      />
      <section className="algorithm-groups">
        {Object.entries(groups).map(([category, items]) => (
          <article className="console-card" key={category}>
            <div className="card-heading">
              <div>
                <span>CATEGORY</span>
                <h2>{category}</h2>
              </div>
            </div>
            <div className="algorithm-list">
              {items?.map((item) => (
                <div key={item.id}>
                  <span className={`state-badge ${item.state}`}>{item.state}</span>
                  <strong>{item.name}</strong>
                  <p>{item.description}</p>
                </div>
              ))}
            </div>
          </article>
        ))}
      </section>
      <article className="console-card learning-note">
        <h2>评测原则</h2>
        <p>
          按时间顺序只使用当前样本之前的窗口，防止未来数据泄漏；数据集记录真值、算法版本、参数、延迟和模型成本。
        </p>
        <code>experiments/evaluate_detectors.py · experiments/train_autoencoder.py</code>
      </article>
    </>
  );
}
