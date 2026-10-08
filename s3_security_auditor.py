"""
AWS Lambda Function: S3SecurityAuditor

Monitors Amazon S3 buckets for public-access security risks.
Triggered by:
- Amazon EventBridge (Scheduled periodic audit or S3 CloudTrail events)
- Direct invocation from backend API

Workflow:
1. Inspects S3 buckets for public access block, policy status, and ACL grants.
2. Identifies publicly accessible buckets.
3. Records security events in Amazon DynamoDB table 'SecurityEvents'.
4. Publishes alerts to Amazon SNS topic.
5. Publishes MQTT command to AWS IoT Core topic 'security/alert/led' to set physical LED to BLINKING.
6. If no public bucket is detected, keeps LED OFF.
"""

import os
import json
import logging
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

# Setup Logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
REGION = os.environ.get("AWS_REGION", "ap-south-1")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE_NAME", "SecurityEvents")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
IOT_ENDPOINT = os.environ.get("AWS_IOT_ENDPOINT", "")
IOT_TOPIC = os.environ.get("AWS_IOT_TOPIC", "security/alert/led")

# Initialize AWS clients
s3_client = boto3.client("s3", region_name=REGION)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns_client = boto3.client("sns", region_name=REGION)

# Initialize IoT Data client if endpoint configured
iot_data = None
if IOT_ENDPOINT:
    endpoint_url = f"https://{IOT_ENDPOINT}" if not IOT_ENDPOINT.startswith("http") else IOT_ENDPOINT
    iot_data = boto3.client("iot-data", endpoint_url=endpoint_url, region_name=REGION)
else:
    try:
        iot_data = boto3.client("iot-data", region_name=REGION)
    except Exception:
        pass

def check_bucket_public_access(bucket_name: str):
    """
    Evaluates whether an S3 bucket is public:
    - Public Access Block configuration
    - Policy Status (IsPublic)
    - ACL grants to AllUsers
    """
    is_public = False
    reasons = []
    risk = "LOW"

    # 1. Inspect Public Access Block
    try:
        pab = s3_client.get_public_access_block(Bucket=bucket_name)
        cfg = pab.get("PublicAccessBlockConfiguration", {})
        if not (cfg.get("BlockPublicAcls") and cfg.get("IgnorePublicAcls") and 
                cfg.get("BlockPublicPolicy") and cfg.get("RestrictPublicBuckets")):
            is_public = True
            reasons.append("Public access block settings are disabled or incomplete")
            risk = "HIGH"
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code == "NoSuchPublicAccessBlockConfiguration":
            is_public = True
            reasons.append("No Public Access Block found (defaults to public access allowed)")
            risk = "HIGH"

    # 2. Inspect Bucket Policy
    try:
        pol_status = s3_client.get_bucket_policy_status(Bucket=bucket_name)
        if pol_status.get("PolicyStatus", {}).get("IsPublic", False):
            is_public = True
            reasons.append("Bucket policy status is PUBLIC")
            risk = "HIGH"
    except ClientError:
        pass

    # 3. Inspect Bucket ACLs
    try:
        acl = s3_client.get_bucket_acl(Bucket=bucket_name)
        for grant in acl.get("Grants", []):
            uri = grant.get("Grantee", {}).get("URI", "")
            perm = grant.get("Permission", "")
            if "AllUsers" in uri:
                is_public = True
                reasons.append(f"Public ACL grant to AllUsers: {perm}")
                if perm in ("WRITE", "FULL_CONTROL"):
                    risk = "CRITICAL"
                else:
                    risk = "HIGH"
    except ClientError as e:
        logger.warning(f"Error checking ACL for {bucket_name}: {e}")

    return is_public, risk, "; ".join(reasons) if reasons else "Bucket is private and secure."

def save_event_to_dynamodb(event_id, bucket_name, is_public, risk_level, led_status, reason):
    """Stores security event in DynamoDB table 'SecurityEvents'."""
    try:
        table = dynamodb.Table(DYNAMODB_TABLE)
        now = datetime.now()
        item = {
            "eventId": event_id,
            "bucketName": bucket_name,
            "region": REGION,
            "publicAccess": is_public,
            "riskLevel": risk_level,
            "eventType": "Public Access Detected" if is_public else "Bucket Scan",
            "ledStatus": led_status,
            "timestamp": now.isoformat(),
            "time": now.strftime("%I:%M %p"),
            "status": "ACTIVE" if is_public else "LOGGED",
            "details": reason
        }
        table.put_item(Item=item)
        logger.info(f"DynamoDB event recorded: {event_id} for bucket {bucket_name}")
    except Exception as e:
        logger.error(f"Failed to record event in DynamoDB: {e}")

def publish_sns_alert(bucket_name, risk_level, reason):
    """Publishes security alert to SNS topic."""
    if not SNS_TOPIC_ARN:
        return
    try:
        subject = f"CRITICAL: Public S3 Bucket Detected ({bucket_name})"
        message = (
            f"SECURITY ALERT FROM CLOUD SECURITY ALERT LAMP\n\n"
            f"Bucket: {bucket_name}\n"
            f"Risk: {risk_level}\n"
            f"Reason: {reason}\n"
            f"Physical Lamp: BLINKING\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message
        )
        logger.info(f"SNS alert sent for {bucket_name}")
    except Exception as e:
        logger.error(f"Failed to publish SNS alert: {e}")

def set_iot_led_state(led_status, reason):
    """Publishes MQTT message to AWS IoT Core topic 'security/alert/led'."""
    if not iot_data:
        return
    try:
        payload = json.dumps({
            "led": "RED",
            "status": led_status,
            "reason": reason
        })
        iot_data.publish(
            topic=IOT_TOPIC,
            qos=1,
            payload=payload.encode("utf-8")
        )
        logger.info(f"Published to AWS IoT Core topic {IOT_TOPIC}: {payload}")
    except Exception as e:
        logger.error(f"Failed to publish to AWS IoT Core: {e}")

def lambda_handler(event, context):
    """
    Main Lambda entry point.
    Accepts optional payload: {"targetBucket": "demo-bucket"}
    """
    logger.info(f"S3SecurityAuditor invoked. Event: {json.dumps(event)}")
    
    target_bucket = event.get("targetBucket") if isinstance(event, dict) else None
    
    # Determine which buckets to audit
    buckets_to_scan = []
    if target_bucket:
        buckets_to_scan = [target_bucket]
    else:
        try:
            resp = s3_client.list_buckets()
            buckets_to_scan = [b["Name"] for b in resp.get("Buckets", [])]
        except Exception as e:
            logger.error(f"Could not list S3 buckets: {e}")
            buckets_to_scan = ["demo-bucket"]

    public_detected = False
    last_public_bucket = None
    last_risk = "LOW"
    now_ms = int(datetime.now().timestamp() * 1000)

    for b_name in buckets_to_scan:
        is_pub, risk, reason = check_bucket_public_access(b_name)
        event_id = f"EVT-LAMBDA-{now_ms}-{b_name[:8]}"
        
        if is_pub:
            public_detected = True
            last_public_bucket = b_name
            last_risk = risk
            
            # Step 5: Store in DynamoDB
            save_event_to_dynamodb(event_id, b_name, True, risk, "BLINKING", reason)
            
            # Step 6: Send SNS alert
            publish_sns_alert(b_name, risk, reason)
            
            # Step 7: Set physical LED state to BLINKING
            set_iot_led_state("BLINKING", f"PUBLIC_S3_BUCKET_{b_name}")

    if not public_detected:
        # Step 8: Keep LED OFF
        set_iot_led_state("OFF", "SYSTEM_SECURE")
        first_bucket = buckets_to_scan[0] if buckets_to_scan else "all-buckets"
        save_event_to_dynamodb(f"EVT-LAMBDA-{now_ms}-SECURE", first_bucket, False, "LOW", "OFF", "Audit passed. System secure.")
        
        return {
            "status": "SECURE",
            "bucket": first_bucket,
            "publicAccess": False,
            "risk": "LOW",
            "ledStatus": "OFF"
        }
    else:
        return {
            "status": "ALERT",
            "bucket": last_public_bucket,
            "publicAccess": True,
            "risk": last_risk,
            "ledStatus": "BLINKING"
        }
