"""人工审批、修复执行和业务恢复验证应用服务。

这是系统安全边界中的关键模块：只有内容哈希一致、审批未过期且幂等键未执行过，
修复步骤才会被交给执行端口。每个关键判断都在代码旁使用中文解释。
"""

from aiops_control.application.real_action_policy import RealActionPolicy
from aiops_control.domain.enums import ActionStatus, PlanStatus
from aiops_control.domain.errors import (
    ApprovalExpiredError,
    EntityNotFoundError,
    IntegrityViolationError,
    InvalidStateTransitionError,
)
from aiops_control.domain.models import (
    ActionRun,
    Approval,
    RemediationStep,
    new_id,
    utc_now,
)
from aiops_control.ports.execution import ActionDispatcher, RecoveryVerifier
from aiops_control.ports.repositories import IncidentRepository, RemediationRepository


class RemediationApplicationService:
    """保证审批、执行和 Incident 状态始终同步。"""

    def __init__(
        self,
        incident_repository: IncidentRepository,
        remediation_repository: RemediationRepository,
        dispatcher: ActionDispatcher,
        recovery_verifier: RecoveryVerifier | None = None,
        real_actions_mode: str = "observe_only",
    ) -> None:
        self._incidents = incident_repository
        self._remediations = remediation_repository
        self._dispatcher = dispatcher
        self._recovery_verifier = recovery_verifier
        self._real_action_policy = RealActionPolicy(real_actions_mode)

    def approve_and_execute(
        self,
        plan_id: str,
        approver: str,
        approved_hash: str,
        idempotency_key: str,
    ) -> ActionRun:
        """批准计划并同步执行，重复请求返回第一次执行记录。

        生产版会将执行下发改为 Agent 长连接上的异步任务；阶段一保留同样的
        幂等和审批数据结构，使用同步端口缩短可演示闭环。
        """

        # 第一步先查幂等键；即使计划已经成功，网络重试也能得到原结果。
        existing = self._remediations.get_action_run_by_key(idempotency_key)
        if existing is not None:
            return existing

        # 计划和 Incident 必须同时存在，否则不能形成完整审计链。
        plan = self._remediations.get_plan(plan_id)
        if plan is None:
            raise EntityNotFoundError(f"修复计划 {plan_id} 不存在")
        incident = self._incidents.get_incident(plan.incident_id)
        if incident is None:
            raise EntityNotFoundError(f"Incident {plan.incident_id} 不存在")

        # 策略校验发生在审批事实落库前，AI、HTTP 或未来队列都不能绕过观察模式。
        self._real_action_policy.validate(plan)

        # 只允许审批等待中的计划，避免同一计划被不同请求反复执行。
        if plan.status is not PlanStatus.PENDING_APPROVAL:
            raise InvalidStateTransitionError(f"计划状态 {plan.status} 不允许审批")
        # 使用服务器 UTC 时间判定过期，不信任客户端提供的时间。
        now = utc_now()
        if now > plan.expires_at:
            plan.status = PlanStatus.EXPIRED
            self._remediations.save_plan(plan)
            raise ApprovalExpiredError("修复计划已经过期，请重新生成")

        # 重新计算服务端计划哈希，阻止审批之后替换命令、参数或目标。
        actual_hash = plan.content_hash()
        if approved_hash != actual_hash:
            raise IntegrityViolationError("批准内容哈希与当前计划不一致")

        # 审批记录是不可变事实，必须先保存再开始任何系统变更。
        approval = Approval(
            id=new_id("approval"),
            plan_id=plan.id,
            approver=approver,
            approved_hash=actual_hash,
            approved_at=now,
        )
        self._remediations.save_approval(approval)
        plan.status = PlanStatus.APPROVED
        incident.start_remediation()
        self._remediations.save_plan(plan)
        self._incidents.save_incident(incident)

        # ActionRun 在执行前落库，进程中断时仍能识别未完成任务。
        action_run = ActionRun(
            id=new_id("run"),
            plan_id=plan.id,
            incident_id=incident.id,
            idempotency_key=idempotency_key,
            approved_hash=actual_hash,
            status=ActionStatus.RUNNING,
            created_at=now,
            started_at=now,
        )
        self._remediations.save_action_run(action_run)
        plan.status = PlanStatus.EXECUTING
        self._remediations.save_plan(plan)

        step_outputs: list[dict[str, str | bool]] = []
        completed_steps: list[RemediationStep] = []
        succeeded = True
        # 严格按计划顺序执行；前一步失败后停止，避免扩大故障影响面。
        for step in plan.steps:
            result = self._dispatcher.execute(step, actual_hash)
            step_outputs.append(
                {
                    "action_type": step.action_type,
                    "target": step.target,
                    "succeeded": result.succeeded,
                    "message": result.message,
                }
            )
            if not result.succeeded:
                succeeded = False
                break
            completed_steps.append(step)

        verification: dict[str, object] | None = None
        if (
            succeeded
            and self._recovery_verifier is not None
            and incident.asset_id.startswith("lab-")
        ):
            verification = self._recovery_verifier.verify(incident.asset_id)
            succeeded = bool(verification.get("healthy"))

        # 只有失败前已经成功且显式声明回滚动作的步骤才进入反向补偿。
        # 反向顺序对应事务补偿语义：后执行的变更必须先撤销，避免依赖关系倒置。
        rollback_outputs: list[dict[str, str | bool]] = []
        rollback_succeeded = False
        if not succeeded:
            rollback_outputs, rollback_succeeded = self._rollback(
                completed_steps,
                actual_hash,
            )

        # 执行输出和最终状态一起持久化，供审计和 UI 查看。
        action_run.output = {
            "steps": step_outputs,
            "rollback": rollback_outputs,
            "verification": verification,
        }
        action_run.finished_at = utc_now()
        if succeeded:
            action_run.status = ActionStatus.SUCCEEDED
        elif rollback_succeeded:
            action_run.status = ActionStatus.ROLLED_BACK
        else:
            action_run.status = ActionStatus.FAILED
        plan.status = PlanStatus.SUCCEEDED if succeeded else PlanStatus.FAILED
        incident.finish(succeeded)
        self._remediations.save_action_run(action_run)
        self._remediations.save_plan(plan)
        self._incidents.save_incident(incident)
        return action_run

    def _rollback(
        self,
        completed_steps: list[RemediationStep],
        approved_hash: str,
    ) -> tuple[list[dict[str, str | bool]], bool]:
        """按反向顺序执行显式补偿，返回审计输出和总体结果。"""

        rollback_steps = [step for step in reversed(completed_steps) if step.rollback_action]
        if not rollback_steps:
            # 没有可回滚动作不能声称已经回滚，交由人工接管失败 Incident。
            return [], False

        outputs: list[dict[str, str | bool]] = []
        all_succeeded = True
        for original_step in rollback_steps:
            # 回滚仍然是类型化动作，并复用用户批准的计划哈希；不生成任何 Shell。
            rollback_step = RemediationStep(
                action_type=original_step.rollback_action or "",
                target=original_step.target,
                arguments=original_step.rollback_arguments,
                expected_result="回滚动作执行成功",
            )
            result = self._dispatcher.execute(rollback_step, approved_hash)
            outputs.append(
                {
                    "action_type": rollback_step.action_type,
                    "target": rollback_step.target,
                    "succeeded": result.succeeded,
                    "message": result.message,
                }
            )
            # 某个补偿失败后仍继续尝试更早的补偿，尽可能缩小残留影响范围。
            all_succeeded = all_succeeded and result.succeeded
        return outputs, all_succeeded
