"""
Sentinel Agent Orchestrator
Agentic loop using Claude tool_use to triage and investigate incidents.
"""
import json
import time
import logging
from datetime import datetime
from typing import Any

import anthropic

from .tools.triage import triage_alert, TRIAGE_TOOL_DEF
from .tools.check_metrics import check_metrics, CHECK_METRICS_TOOL_DEF
from .tools.query_logs import query_logs, QUERY_LOGS_TOOL_DEF
from .tools.run_runbook import run_runbook, RUN_RUNBOOK_TOOL_DEF
from .tools.draft_postmortem import draft_postmortem, DRAFT_POSTMORTEM_TOOL_DEF
from .tools.notify import notify_slack, NOTIFY_TOOL_DEF
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

TOOLS = [
    TRIAGE_TOOL_DEF,
    CHECK_METRICS_TOOL_DEF,
    QUERY_LOGS_TOOL_DEF,
    RUN_RUNBOOK_TOOL_DEF,
    DRAFT_POSTMORTEM_TOOL_DEF,
    NOTIFY_TOOL_DEF,
]

TOOL_REGISTRY = {
    "triage_alert": triage_alert,
    "check_metrics": check_metrics,
    "query_logs": query_logs,
    "run_runbook": run_runbook,
    "draft_postmortem": draft_postmortem,
    "notify_slack": notify_slack,
}

MAX_ITERATIONS = 12


def run_agent(alert: dict) -> dict:
    """
    Run the Sentinel agentic loop for a given alert payload.
    Returns a structured incident report.
    """
    client = anthropic.Anthropic()

    incident_id = f"INC-{int(time.time())}"
    started_at = datetime.utcnow().isoformat()

    user_message = f"""
New alert received. Investigate and respond.

Alert payload:
```json
{json.dumps(alert, indent=2)}
```

Incident ID: {incident_id}
Received at: {started_at} UTC

Follow your SRE protocol:
1. Triage the alert (severity, service, probable cause)
2. Pull relevant metrics and logs
3. Run appropriate runbook steps if applicable
4. Draft a postmortem skeleton if severity is P1 or P2
5. Send a structured Slack notification with your findings
"""

    messages = [{"role": "user", "content": user_message}]
    tool_calls_log = []
    iterations = 0

    logger.info(f"[{incident_id}] Starting Sentinel agent loop")

    while iterations < MAX_ITERATIONS:
        iterations += 1
        logger.info(f"[{incident_id}] Iteration {iterations}")

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Collect assistant message
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.info(f"[{incident_id}] Agent finished after {iterations} iterations")
            break

        if response.stop_reason != "tool_use":
            logger.warning(f"[{incident_id}] Unexpected stop reason: {response.stop_reason}")
            break

        # Process all tool calls in this response
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            tool_use_id = block.id

            logger.info(f"[{incident_id}] Tool call: {tool_name}({json.dumps(tool_input)[:120]}...)")

            tool_fn = TOOL_REGISTRY.get(tool_name)
            if not tool_fn:
                result = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    result = tool_fn(**tool_input)
                except Exception as e:
                    result = {"error": str(e), "tool": tool_name}

            tool_calls_log.append({
                "iteration": iterations,
                "tool": tool_name,
                "input": tool_input,
                "output": result,
            })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

    # Extract final text summary from last assistant message
    final_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            final_text = block.text
            break

    return {
        "incident_id": incident_id,
        "started_at": started_at,
        "finished_at": datetime.utcnow().isoformat(),
        "iterations": iterations,
        "alert": alert,
        "tool_calls": tool_calls_log,
        "summary": final_text,
    }
