# Architecture Overview

## System Design

RAG Shield is a serverless security system that scans documents before they enter your RAG pipeline.

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                │
│                           │                                 │
│                           ▼                                 │
│                    Upload Document                          │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    S3 Raw Data Bucket                       │
│                  (EventBridge Enabled)                      │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    EventBridge Rule                         │
│              (Triggers on S3 Object Created)                │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Lambda Function                          │
│                                                             │
│  1. Download file from S3                                   │
│  2. Extract text content                                    │
│  3. Call Bedrock Guardrails                                 │
│  4. Analyze response                                        │
│  5. Tag file (Clean/Malicious)                              │
│  6. Take action based on result                             │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
         ┌──────────┐           ┌──────────┐
         │  CLEAN   │           │ MALICIOUS│
         └────┬─────┘           └────┬─────┘
              │                      │
              ▼                      ▼
    ┌─────────────────┐    ┌─────────────────┐
    │ Tag: Clean      │    │ Tag: Malicious  │
    │ Allow Access    │    │ Quarantine      │
    │ Log to DynamoDB │    │ Security Hub    │
    │                 │    │ SNS Alert       │
    │                 │    │ Log to DynamoDB │
    └─────────────────┘    └─────────────────┘
```

---

## Components

### 1. Bedrock Guardrail

**Purpose:** Detects prompt injection attacks using ML

**Configuration:**
- Filter Type: `PROMPT_ATTACK`
- Strength: `HIGH`
- Auto-created by CloudFormation

**How It Works:**
- Analyzes text for malicious patterns
- Returns `GUARDRAIL_INTERVENED` if threat detected
- Returns `NONE` if content is clean

### 2. Lambda Function

**Purpose:** Orchestrates the scanning process

**Runtime:** Python 3.12  
**Memory:** 512 MB  
**Timeout:** 60 seconds

**Process:**
1. Triggered by S3 upload via EventBridge
2. Downloads file from S3
3. Extracts text (UTF-8 decode)
4. Calls Bedrock Guardrails API
5. Tags file based on result
6. Handles clean/malicious files differently
7. Logs to DynamoDB

**Code:** Embedded inline in CloudFormation template

### 3. S3 Buckets

#### Raw Data Bucket
- Where users upload documents
- EventBridge notifications enabled
- Versioning enabled
- Public access blocked

#### Forensic Bucket
- Stores quarantined malicious files
- 90-day Object Lock (GOVERNANCE mode)
- Organized by date: `quarantine/YYYY/MM/DD/SCAN-ID/`
- Versioning enabled

#### KB Ingestion Bucket (DualBucket only)
- Receives clean files only
- Bedrock KB reads from here
- No malicious files ever present

### 4. DynamoDB Table

**Purpose:** Audit log of all scans

**Schema:**
- `scan_id` (String, Primary Key)
- `timestamp` (String, Sort Key)
- `bucket` (String)
- `key` (String)
- `status` (String: Clean/Malicious)
- `is_malicious` (Boolean)
- `deployment_mode` (String)
- `guardrail_action` (String)

**Billing:** On-Demand (pay per request)

### 5. SNS Topic

**Purpose:** Email alerts for malicious files

**Subscribers:** Email addresses (configured via parameter)

**Message Format:**
```
Subject: 🚨 Malicious Document Detected

File: document.txt
Bucket: rag-shield-raw-data-123456789012
Scan ID: abc-123-def-456
Quarantined: s3://forensic-bucket/quarantine/...
```

### 6. EventBridge Rule

**Purpose:** Triggers Lambda on S3 uploads

**Event Pattern:**
```json
{
  "source": ["aws.s3"],
  "detail-type": ["Object Created"],
  "detail": {
    "bucket": {
      "name": ["raw-data-bucket-name"]
    }
  }
}
```

### 7. IAM Roles

**Lambda Execution Role:**
- S3: GetObject, PutObjectTagging, CopyObject
- Bedrock: ApplyGuardrail
- DynamoDB: PutItem
- SNS: Publish
- Security Hub: BatchImportFindings
- CloudWatch Logs: CreateLogGroup, CreateLogStream, PutLogEvents

**Bedrock KB Role (SingleBucket):**
- S3: GetObject, ListBucket
- Condition: `s3:ExistingObjectTag/ScanStatus = "Clean"`

---

## Deployment Modes

### SingleBucket Mode (Default)

```
User → Raw Bucket → Scan → Tag (Clean/Malicious)
                              │
                              ├─ Clean: ABAC allows KB access
                              └─ Malicious: ABAC blocks KB access
```

**Pros:**
- Simpler architecture
- Faster (no file copying)
- Cheaper (less S3 operations)

**Cons:**
- Malicious files remain in bucket (tagged)
- Requires ABAC policy on KB role

### DualBucket Mode

```
User → Raw Bucket → Scan → Decision
                              │
                              ├─ Clean: Copy to KB Bucket
                              └─ Malicious: Do NOT copy
```

**Pros:**
- Physical separation
- KB bucket only has clean files
- No ABAC policy needed

**Cons:**
- More complex
- Slower (file copying)
- Higher cost (2x storage)

---

## Data Flow

### Clean File Flow

1. User uploads `document.txt` to raw bucket
2. EventBridge detects upload
3. Lambda triggered with S3 event
4. Lambda downloads file
5. Lambda calls Bedrock Guardrails
6. Guardrails returns `action: NONE` (clean)
7. Lambda tags file: `ScanStatus=Clean`
8. Lambda logs to DynamoDB
9. **SingleBucket:** KB can read (ABAC allows)
10. **DualBucket:** Lambda copies to KB bucket

### Malicious File Flow

1. User uploads `malicious.txt` to raw bucket
2. EventBridge detects upload
3. Lambda triggered with S3 event
4. Lambda downloads file
5. Lambda calls Bedrock Guardrails
6. Guardrails returns `action: GUARDRAIL_INTERVENED`
7. Lambda tags file: `ScanStatus=Malicious`
8. Lambda copies to forensic bucket
9. Lambda creates Security Hub finding
10. Lambda sends SNS alert
11. Lambda logs to DynamoDB
12. **SingleBucket:** KB cannot read (ABAC blocks)
13. **DualBucket:** File NOT copied to KB bucket

---

## Security Controls

### Layer 1: Detection
- Bedrock Guardrails ML model
- HIGH strength filtering
- Continuous AWS updates

### Layer 2: Access Control
- **SingleBucket:** ABAC policy (tag-based)
- **DualBucket:** Physical separation

### Layer 3: Quarantine
- Forensic bucket with Object Lock
- 90-day retention
- Immutable for investigation

### Layer 4: Alerting
- Security Hub findings
- SNS email notifications
- Real-time threat awareness

### Layer 5: Audit
- Complete DynamoDB trail
- All scans logged
- Compliance-ready

---

## Scalability

### Automatic Scaling
- Lambda: Scales to 1000 concurrent executions
- DynamoDB: On-Demand scales automatically
- S3: Unlimited storage
- EventBridge: Handles millions of events

### Performance
- Scan time: 1-3 seconds per file
- Throughput: Limited by Lambda concurrency
- Can process thousands of files per minute

### Limits
- Lambda timeout: 60 seconds
- Lambda memory: 512 MB
- File size: Limited by Lambda memory
- For large files: Increase Lambda memory

---

## Cost Breakdown

### Per 1000 Scans

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 1000 invocations × 2s × 512MB | $0.02 |
| Bedrock | 1000 Guardrail API calls | $0.75 |
| S3 | 10 GB storage + requests | $0.25 |
| DynamoDB | 1000 writes + 100 reads | $0.30 |
| EventBridge | 1000 events | $0.00 |
| SNS | 10 alerts | $0.00 |
| CloudWatch | 1 GB logs | $0.50 |
| **Total** | | **~$1.82** |

### Cost Optimization
- Reduce Lambda memory for small files
- Enable S3 Intelligent-Tiering
- Reduce CloudWatch log retention
- Use DynamoDB On-Demand (already default)

---

## Monitoring

### CloudWatch Metrics
- Lambda invocations
- Lambda errors
- Lambda duration
- DynamoDB read/write capacity

### CloudWatch Logs
- Lambda execution logs
- Scan results
- Error messages

### Security Hub
- Malicious file findings
- Severity: HIGH
- Automatic aggregation

### DynamoDB Audit
- Complete scan history
- Query by date, status, file
- Compliance reporting

---

## High Availability

### Multi-AZ
- Lambda: Runs in multiple AZs
- DynamoDB: Multi-AZ by default
- S3: 99.999999999% durability

### Disaster Recovery
- S3 versioning enabled
- DynamoDB point-in-time recovery (optional)
- CloudFormation for infrastructure as code

### Backup
- Forensic bucket: 90-day retention
- DynamoDB: Continuous backups (optional)
- CloudFormation template in version control

---

## Compliance

### Audit Trail
- DynamoDB logs all scans
- CloudWatch logs all executions
- S3 access logs (optional)
- CloudTrail API calls (optional)

### Data Retention
- Forensic: 90 days (configurable)
- DynamoDB: Indefinite (configurable)
- CloudWatch: 7 days (configurable)

### Encryption
- S3: SSE-S3 (default)
- DynamoDB: Encryption at rest
- Lambda: Environment variables encrypted
- SNS: In-transit encryption

---

## Future Enhancements

Potential improvements:
- PDF/DOCX text extraction
- Multi-language support
- Custom detection rules
- Webhook notifications
- Dashboard UI
- Batch scanning API
- Integration with other AI services
