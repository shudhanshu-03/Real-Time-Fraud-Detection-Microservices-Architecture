"""
Templates for Notifications
"""

EMAIL_TEMPLATE = """
<html>
<body>
    <h2>Fraud Alert: {severity}</h2>
    <p>We detected suspicious activity on your account.</p>
    <p><strong>Alert ID:</strong> {alert_id}</p>
    <p><strong>Transaction ID:</strong> {transaction_id}</p>
    <p><strong>Amount:</strong> {amount}</p>
    <p><strong>Merchant:</strong> {merchant}</p>
    <p><strong>Risk Score:</strong> {risk_score}</p>
    <br/>
    <p>Please review this transaction immediately.</p>
</body>
</html>
"""

SMS_TEMPLATE = "FRAUD ALERT: Suspicious transaction {transaction_id} for {amount} at {merchant}. Reply YES if valid, NO if unauthorized."

def get_slack_blocks(alert_id: str, severity: str, amount: str, merchant: str, risk_score: str):
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 Fraud Alert ({severity})"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Alert ID:*\n{alert_id}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Risk Score:*\n{risk_score}"
                }
            ]
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Amount:*\n{amount}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Merchant:*\n{merchant}"
                }
            ]
        }
    ]
