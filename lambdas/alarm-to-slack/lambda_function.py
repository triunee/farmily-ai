"""
alarm-to-slack Lambda
CloudWatch Alarm → SNS prod-cloudwatch-alerts → 이 Lambda → Slack Webhook
"""
import json
import os
import urllib.request

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

ALARM_EMOJI = {
    "ALARM": "🚨",
    "OK":    "✅",
    "INSUFFICIENT_DATA": "⚠️",
}

ALARM_COLOR = {
    "ALARM": "#FF0000",
    "OK":    "#36A64F",
    "INSUFFICIENT_DATA": "#FFA500",
}

KR_ALARM_NAMES = {
    "agentcore-job-failed":       "콘텐츠 생성 실패 감지",
    "agentcore-task-missing":     "AgentCore 태스크 다운",
    "agentcore-slow-response":    "AgentCore 응답 지연",
    "agentcore-success-rate-low": "콘텐츠 생성 성공률 저하",
    "bedrock-throttle":           "Bedrock 스로틀 발생",
    "bedrock-token-spike":        "토큰 사용량 급증",
    "rds-connections-high":       "RDS 커넥션 높음",
    "ecs-cpu-high":               "ECS CPU 높음",
    "ecs-memory-high":            "ECS 메모리 높음",
    "rds-cpu-high":               "RDS CPU 높음",
}


def lambda_handler(event, context):
    for record in event.get("Records", []):
        raw = record.get("Sns", {}).get("Message", "{}")
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            msg = {"AlarmName": "unknown", "NewStateValue": "ALARM",
                   "AlarmDescription": raw, "NewStateReason": ""}

        alarm_name  = msg.get("AlarmName", "unknown")
        new_state   = msg.get("NewStateValue", "ALARM")
        old_state   = msg.get("OldStateValue", "")
        description = msg.get("AlarmDescription", "")
        reason      = msg.get("NewStateReason", "")
        region      = msg.get("AWSAccountId", "")
        timestamp   = msg.get("StateChangeTime", "")

        kr_name = KR_ALARM_NAMES.get(alarm_name, alarm_name)
        emoji   = ALARM_EMOJI.get(new_state, "❓")
        color   = ALARM_COLOR.get(new_state, "#888888")

        # KST 변환 (UTC+9)
        kst_time = timestamp
        if timestamp and "T" in timestamp:
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                kst = dt.astimezone(timezone(timedelta(hours=9)))
                kst_time = kst.strftime("%Y-%m-%d %H:%M:%S KST")
            except Exception:
                pass

        payload = {
            "attachments": [
                {
                    "color": color,
                    "blocks": [
                        {
                            "type": "header",
                            "text": {
                                "type": "plain_text",
                                "text": f"{emoji} [{new_state}] {kr_name}"
                            }
                        },
                        {
                            "type": "section",
                            "fields": [
                                {"type": "mrkdwn", "text": f"*알람명*\n`{alarm_name}`"},
                                {"type": "mrkdwn", "text": f"*상태 변화*\n{old_state} → {new_state}"},
                                {"type": "mrkdwn", "text": f"*설명*\n{description or '-'}"},
                                {"type": "mrkdwn", "text": f"*시각*\n{kst_time}"},
                            ]
                        },
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": f"*원인*\n{reason[:300] if reason else '-'}"}
                        }
                    ]
                }
            ]
        }

        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)

    return {"statusCode": 200}
