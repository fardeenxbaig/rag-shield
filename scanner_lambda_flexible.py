"""
Poisoned RAG Quarantine Scanner - Flexible Deployment
Supports both SingleBucket and DualBucket modes
"""

import json
import boto3
import os
import hashlib
import logging
from datetime import datetime
from io import BytesIO

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS clients
s3 = boto3.client('s3')
bedrock_runtime = boto3.client('bedrock-runtime')
securityhub = boto3.client('securityhub')
sns = boto3.client('sns')
dynamodb = boto3.resource('dynamodb')

# Environment variables
AUDIT_TABLE_NAME = os.environ['AUDIT_TABLE_NAME']
FORENSIC_BUCKET = os.environ['FORENSIC_BUCKET_NAME']
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
GUARDRAIL_ID = os.environ.get('GUARDRAIL_ID')
GUARDRAIL_VERSION = os.environ.get('GUARDRAIL_VERSION', 'DRAFT')
DEPLOYMENT_MODE = os.environ.get('DEPLOYMENT_MODE', 'SingleBucket')  # SingleBucket or DualBucket
KB_INGESTION_BUCKET = os.environ.get('KB_INGESTION_BUCKET', '')  # Only for DualBucket mode

# DynamoDB table
audit_table = dynamodb.Table(AUDIT_TABLE_NAME)


def lambda_handler(event, context):
    """Main Lambda handler"""
    scan_id = context.aws_request_id
    logger.info(f"Scan started - ID: {scan_id}")
    logger.info(f"Deployment Mode: {DEPLOYMENT_MODE}")
    
    try:
        # Extract S3 event details from EventBridge
        bucket = event['detail']['bucket']['name']
        key = event['detail']['object']['key']
        
        logger.info(f"Processing: s3://{bucket}/{key}")
        
        # Download and extract text
        text_content = extract_text_from_s3(bucket, key)
        
        if not text_content:
            logger.warning(f"Empty file: {key}")
            tag_object(bucket, key, 'Empty', scan_id)
            create_audit_log(scan_id, bucket, key, 'Empty', False, 0.0, None, None)
            return {'statusCode': 200, 'body': 'Empty file'}
        
        # Calculate file hash
        file_hash = hashlib.sha256(text_content.encode()).hexdigest()
        
        # Scan for threats using Bedrock Guardrails
        is_malicious, confidence, threat_details = scan_for_threats(text_content)
        
        if is_malicious:
            handle_malicious_file(bucket, key, scan_id, confidence, threat_details, file_hash)
        else:
            handle_clean_file(bucket, key, scan_id, confidence, file_hash)
        
        # Create audit log
        create_audit_log(scan_id, bucket, key, 
                        'Malicious' if is_malicious else 'Clean',
                        is_malicious, confidence, threat_details, file_hash)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'scan_id': scan_id,
                'status': 'Malicious' if is_malicious else 'Clean',
                'confidence': confidence
            })
        }
        
    except Exception as e:
        logger.error(f"Scan failed: {str(e)}", exc_info=True)
        return {'statusCode': 500, 'body': str(e)}


def extract_text_from_s3(bucket, key):
    """Download file from S3 and extract text content"""
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read()
        
        # Determine file type and extract text
        if key.lower().endswith('.txt'):
            return content.decode('utf-8', errors='ignore')
        elif key.lower().endswith('.pdf'):
            return extract_text_from_pdf(content)
        elif key.lower().endswith('.docx'):
            return extract_text_from_docx(content)
        else:
            # Try as plain text
            return content.decode('utf-8', errors='ignore')
            
    except Exception as e:
        logger.error(f"Text extraction failed: {str(e)}")
        return None


def extract_text_from_pdf(content):
    """Extract text from PDF"""
    try:
        import PyPDF2
        pdf_file = BytesIO(content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except Exception as e:
        logger.error(f"PDF extraction failed: {str(e)}")
        return None


def extract_text_from_docx(content):
    """Extract text from DOCX"""
    try:
        import docx
        doc_file = BytesIO(content)
        doc = docx.Document(doc_file)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text
    except Exception as e:
        logger.error(f"DOCX extraction failed: {str(e)}")
        return None


def scan_for_threats(text_content):
    """
    Scan text using Bedrock Guardrails for prompt injection.
    Returns: (is_malicious, confidence_score, threat_details)
    """
    try:
        logger.info(f"Starting threat scan with Guardrail ID: {GUARDRAIL_ID}")
        
        if not GUARDRAIL_ID:
            logger.warning("No Guardrail ID configured - skipping Bedrock scan")
            return False, 0.0, None
        
        # Use Bedrock Guardrails ApplyGuardrail API
        response = bedrock_runtime.apply_guardrail(
            guardrailIdentifier=GUARDRAIL_ID,
            guardrailVersion=GUARDRAIL_VERSION,
            source='INPUT',
            content=[{
                'text': {
                    'text': text_content[:10000]  # Limit to first 10k chars
                }
            }]
        )
        
        logger.info(f"Guardrail response: {json.dumps(response, default=str)}")
        
        # Check for prompt attack detection
        action = response.get('action')
        assessments = response.get('assessments', [])
        
        if action == 'GUARDRAIL_INTERVENED':
            # Extract threat details from contentPolicy
            for assessment in assessments:
                content_policy = assessment.get('contentPolicy', {})
                filters = content_policy.get('filters', [])
                
                for filter_item in filters:
                    if filter_item.get('type') == 'PROMPT_ATTACK' and filter_item.get('detected'):
                        confidence_level = filter_item.get('confidence', 'UNKNOWN')
                        # Map confidence levels to scores
                        confidence_map = {'HIGH': 0.9, 'MEDIUM': 0.6, 'LOW': 0.3}
                        confidence_score = confidence_map.get(confidence_level, 0.5)
                        
                        threat_details = {
                            'type': 'PROMPT_INJECTION',
                            'confidence_level': confidence_level,
                            'filter_strength': filter_item.get('filterStrength'),
                            'action': action
                        }
                        logger.warning(f"THREAT DETECTED: {threat_details}")
                        return True, confidence_score, threat_details
        
        # No threats detected
        return False, 0.0, None
        
    except Exception as e:
        logger.error(f"Threat scan failed: {str(e)}")
        # Fail secure - treat as suspicious
        return True, 0.5, {'type': 'SCAN_ERROR', 'error': str(e)}


def handle_malicious_file(bucket, key, scan_id, confidence, threat_details, file_hash):
    """Handle detected malicious file"""
    logger.warning(f"MALICIOUS FILE DETECTED: {key} (confidence: {confidence})")
    
    # Tag as malicious
    tag_object(bucket, key, 'Malicious', scan_id)
    
    # Quarantine to forensic bucket
    quarantine_file(bucket, key, scan_id)
    
    # Create Security Hub finding
    create_security_hub_finding(bucket, key, scan_id, confidence, threat_details)
    
    # Send SNS alert
    if SNS_TOPIC_ARN:
        send_alert(bucket, key, scan_id, confidence, threat_details)


def handle_clean_file(bucket, key, scan_id, confidence, file_hash):
    """Handle clean file"""
    logger.info(f"CLEAN FILE: {key}")
    
    # Tag as clean - allows Bedrock Knowledge Base to ingest
    tag_object(bucket, key, 'Clean', scan_id)
    
    # DualBucket mode: Copy to KB ingestion bucket
    if DEPLOYMENT_MODE == 'DualBucket' and KB_INGESTION_BUCKET:
        copy_to_kb_bucket(bucket, key, scan_id)


def copy_to_kb_bucket(source_bucket, source_key, scan_id):
    """Copy clean file to KB ingestion bucket (DualBucket mode only)"""
    try:
        logger.info(f"Copying clean file to KB bucket: {source_key}")
        
        # Copy object to KB bucket
        s3.copy_object(
            CopySource={'Bucket': source_bucket, 'Key': source_key},
            Bucket=KB_INGESTION_BUCKET,
            Key=source_key,
            TaggingDirective='COPY',
            MetadataDirective='COPY'
        )
        
        logger.info(f"File copied to KB bucket: s3://{KB_INGESTION_BUCKET}/{source_key}")
        
    except Exception as e:
        logger.error(f"Failed to copy to KB bucket: {str(e)}")


def tag_object(bucket, key, status, scan_id):
    """Apply S3 tags to object"""
    try:
        s3.put_object_tagging(
            Bucket=bucket,
            Key=key,
            Tagging={
                'TagSet': [
                    {'Key': 'ScanStatus', 'Value': status},
                    {'Key': 'ScanId', 'Value': scan_id},
                    {'Key': 'ScanTimestamp', 'Value': datetime.utcnow().isoformat()}
                ]
            }
        )
        logger.info(f"Tagged {key} as {status}")
    except Exception as e:
        logger.error(f"Tagging failed: {str(e)}")


def quarantine_file(bucket, key, scan_id):
    """Copy malicious file to forensic bucket with Object Lock"""
    try:
        now = datetime.utcnow()
        forensic_key = f"quarantine/{now.year}/{now.month:02d}/{now.day:02d}/{scan_id}/{key.split('/')[-1]}"
        
        s3.copy_object(
            CopySource={'Bucket': bucket, 'Key': key},
            Bucket=FORENSIC_BUCKET,
            Key=forensic_key,
            TaggingDirective='COPY',
            MetadataDirective='COPY'
        )
        
        logger.info(f"Quarantined to: s3://{FORENSIC_BUCKET}/{forensic_key}")
        
    except Exception as e:
        logger.error(f"Quarantine failed: {str(e)}")


def create_security_hub_finding(bucket, key, scan_id, confidence, threat_details):
    """Create Security Hub finding for malicious file"""
    try:
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = os.environ['AWS_REGION']
        
        finding = {
            'SchemaVersion': '2018-10-08',
            'Id': f"{scan_id}/{key}",
            'ProductArn': f'arn:aws:securityhub:{region}:{account_id}:product/{account_id}/default',
            'GeneratorId': 'poisoned-rag-scanner',
            'AwsAccountId': account_id,
            'Types': ['Software and Configuration Checks/Vulnerabilities/Prompt Injection'],
            'CreatedAt': datetime.utcnow().isoformat() + 'Z',
            'UpdatedAt': datetime.utcnow().isoformat() + 'Z',
            'Severity': {
                'Label': 'HIGH' if confidence > 0.8 else 'MEDIUM',
                'Normalized': int(confidence * 100)
            },
            'Title': 'Prompt Injection Attack Detected in RAG Document',
            'Description': f'Malicious content detected in document: s3://{bucket}/{key}. '
                          f'Confidence: {confidence:.2%}. Threat type: {threat_details.get("type")}',
            'Resources': [{
                'Type': 'AwsS3Object',
                'Id': f'arn:aws:s3:::{bucket}/{key}',
                'Region': region
            }],
            'Compliance': {'Status': 'FAILED'},
            'Remediation': {
                'Recommendation': {
                    'Text': 'File has been quarantined. Review forensic bucket for analysis.',
                    'Url': f'https://s3.console.aws.amazon.com/s3/buckets/{FORENSIC_BUCKET}'
                }
            }
        }
        
        securityhub.batch_import_findings(Findings=[finding])
        logger.info(f"Security Hub finding created: {scan_id}")
        
    except Exception as e:
        logger.error(f"Security Hub finding failed: {str(e)}")


def send_alert(bucket, key, scan_id, confidence, threat_details):
    """Send SNS alert for malicious file"""
    try:
        message = {
            'alert_type': 'PROMPT_INJECTION_DETECTED',
            'scan_id': scan_id,
            'file': f's3://{bucket}/{key}',
            'confidence': f'{confidence:.2%}',
            'threat_type': threat_details.get('type'),
            'deployment_mode': DEPLOYMENT_MODE,
            'timestamp': datetime.utcnow().isoformat(),
            'action_taken': 'File quarantined and tagged as Malicious'
        }
        
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f'🚨 Prompt Injection Detected - {key}',
            Message=json.dumps(message, indent=2)
        )
        logger.info(f"SNS alert sent: {scan_id}")
        
    except Exception as e:
        logger.error(f"SNS alert failed: {str(e)}")


def create_audit_log(scan_id, bucket, key, status, is_malicious, confidence, threat_details, file_hash):
    """Create audit log entry in DynamoDB"""
    try:
        audit_table.put_item(
            Item={
                'scan_id': scan_id,
                'timestamp': datetime.utcnow().isoformat(),
                'bucket': bucket,
                'key': key,
                'status': status,
                'is_malicious': is_malicious,
                'confidence': str(confidence),
                'threat_type': threat_details.get('type') if threat_details else None,
                'file_hash': file_hash,
                'deployment_mode': DEPLOYMENT_MODE
            }
        )
        logger.info(f"Audit log created: {scan_id}")
        
    except Exception as e:
        logger.error(f"Audit log failed: {str(e)}")
