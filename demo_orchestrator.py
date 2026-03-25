"""
Sentinel Demo Orchestrator
Simulates the full agentic loop without an Anthropic API key.
Useful for POC demos, CI tests, and GitHub demos where no key is available.
Set SENTINEL_DEMO_MODE=1 to activate.
"""
import time
import json
from datetime import datetime

from agent.tools.triage import triage_alert
from agent.tools.check_metrics import check_metrics
from agent.tools.query_logs import query_logs
from agent.tools.run_runbook import run_runbook
from agent.tools.draft_postmortem import draft_postmortem
from agent.tools.notify import notify_slack


def run_demo_agent(alert: dict) -> dict:
    """
    Execute the full SRE investigation pipeline in demo mode.
    Calls every tool in the correct order, just as Claude would orchestrate them.
    Returns the same schema as the real agent.
    """
    incident_id = f"INC-DEMO-{int(time.time())}"
    started_at = datetime.utcnow().isoformat()
    tool_calls_log = []

    def call_tool(tool_name: str, fn, **kwargs):
        result = fn(**kwargs)
        tool_calls_log.append({
            "iteration": len(tool_calls_log) + 1,
            "tool": tool_name,
            "input": kwargs,
            "output": result,
        })
        return result

    alert_name  = alert.get("alert_name", "UnknownAlert")
    service     = alert.get("service", "unknown-service")
    environment = alert.get("environment", "prod")
    labels      = alert.get("labels", {})

    # ── Step 1: Triage ────────────────────────────────
    triage = call_tool("triage_alert", triage_alert,
        alert_name=alert_name,
        service=service,
        environment=environment,
        labels=labels,
    )
    severity = triage["severity"]
    category = triage["failure_category"]
    runbook_name = triage.get("suggested_runbook")

    # ── Step 2: Metrics ───────────────────────────────
    metrics = call_tool("check_metrics", check_metrics,
        service=service,
        window_minutes=30,
        metrics=["cpu_percent", "memory_mb", "error_rate", "req_per_sec", "latency_p99_ms"],
    )

    # ── Step 3: Logs ──────────────────────────────────
    logs = call_tool("query_logs", query_logs,
        service=service,
        level="ERROR",
        window_minutes=15,
    )

    # ── Step 4: Runbook ───────────────────────────────
    rb = None
    if runbook_name:
        rb = call_tool("run_runbook", run_runbook,
            runbook_name=runbook_name,
            service=service,
        )

    # ── Step 5: Postmortem for P1/P2 ─────────────────
    pm = None
    if severity in ("P1", "P2"):
        pm = call_tool("draft_postmortem", draft_postmortem,
            incident_id=incident_id,
            service=service,
            severity=severity,
            failure_category=category,
            detected_at=started_at,
        )

    # ── Step 6: Slack notification ────────────────────
    anomalies = metrics.get("summary", {}).get("anomalous_metrics", [])
    log_pattern = logs.get("error_pattern_detected", "unknown")
    log_count = logs.get("total_errors_found", 0)

    evidence = [
        f"Error pattern: {log_pattern} ({log_count} occurrences in last 15m)",
    ]
    for metric in anomalies:
        md = metrics["metrics"].get(metric, {})
        evidence.append(f"{metric}: current={md.get('current')} max={md.get('max_last_30m')} (anomaly detected)")

    actions = []
    if rb:
        for action in (rb.get("recommended_actions") or []):
            if isinstance(action, dict):
                prefix = "⚠️ [APPROVAL REQUIRED] " if action.get("requires_approval") else ""
                actions.append(prefix + action["action"])
            else:
                actions.append(str(action))
    if not actions:
        actions = [
            f"Review {service} pod logs and recent deployments",
            f"Check downstream dependencies of {service}",
            "Escalate to on-call lead if not resolved in 15 minutes",
        ]

    root_cause = (
        rb["findings"] if rb
        else f"Detected {log_pattern} pattern in {service}. {metrics['summary'].get('recommendation', '')}"
    )

    notify = call_tool("notify_slack", notify_slack,
        severity=severity,
        service=service,
        title=f"{category.replace('-', ' ').title()} on {service}",
        root_cause=root_cause[:300],
        evidence=evidence[:4],
        actions=actions[:4],
        blast_radius=f"Services depending on {service}",
        eta_resolution="15-45 minutes" if severity in ("P1","P2") else "60-120 minutes",
    )

    # Build summary text (as Claude would write it)
    summary = f"""**Incident {incident_id} — {severity} {alert_name}**

Triage complete. {service} in {environment} is experiencing **{category}**.
On-call owner: {triage['oncall_owner']}.

Root cause hypothesis: {root_cause[:200]}

Metrics show {len(anomalies)} anomalous signals: {', '.join(anomalies) or 'under investigation'}.
Log analysis found **{log_count} occurrences** of `{log_pattern}` pattern in the last 15 minutes.

{f'Runbook `{runbook_name}` executed: {len(rb["steps_executed"])} diagnostic steps completed.' if rb else ''}
{f'Postmortem draft created: {pm["confluence_url"]}' if pm else ''}

Slack notification posted to #incidents. Recommended actions:
{chr(10).join(f"  {i+1}. {a}" for i, a in enumerate(actions[:4]))}

ETA to resolution: {'15-45 minutes' if severity in ('P1','P2') else '60-120 minutes'}."""

    return {
        "incident_id": incident_id,
        "started_at": started_at,
        "finished_at": datetime.utcnow().isoformat(),
        "iterations": len(tool_calls_log),
        "alert": alert,
        "tool_calls": tool_calls_log,
        "summary": summary,
        "demo_mode": True,
    }
