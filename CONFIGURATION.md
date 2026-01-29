# Configuration Guide

## Deployment Parameters

### Required Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `AlertEmail` | Email for security alerts | `security@company.com` |

### Optional Parameters

#### Deployment Mode

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `DeploymentMode` | `SingleBucket` or `DualBucket` | `SingleBucket` | How files are processed |

**SingleBucket:**
- Files scanned in-place
- Access controlled by tags
- Simpler, recommended

**DualBucket:**
- Clean files copied to separate bucket
- Physical isolation
- More secure

#### Custom Resource Names

Leave empty for auto-generated names, or provide custom names:

| Parameter | Description | Pattern |
|-----------|-------------|---------|
| `RawDataBucketName` | Raw data bucket | lowercase, hyphens, 3-63 chars |
| `ForensicBucketName` | Forensic bucket | lowercase, hyphens, 3-63 chars |
| `KBIngestionBucketName` | KB bucket (DualBucket only) | lowercase, hyphens, 3-63 chars |
| `LambdaFunctionName` | Lambda function | alphanumeric, hyphens, underscores |
| `DynamoDBTableName` | Audit table | alphanumeric, dots, hyphens, underscores |
| `SNSTopicName` | Alert topic | alphanumeric, hyphens, underscores |
| `GuardrailName` | Bedrock Guardrail | any string |

#### Advanced Options

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `GuardrailId` | Guardrail ID | (empty) | Use existing guardrail instead of creating new |
| `CreateBedrockKB` | `true` or `false` | `false` | Auto-create Bedrock Knowledge Base |

---

## Example Deployments

### Minimal (Recommended)

```bash
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters ParameterKey=AlertEmail,ParameterValue=security@company.com \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### DualBucket Mode

```bash
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=DeploymentMode,ParameterValue=DualBucket \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Custom Names

```bash
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
    ParameterKey=RawDataBucketName,ParameterValue=acme-rag-raw \
    ParameterKey=ForensicBucketName,ParameterValue=acme-rag-forensic \
    ParameterKey=LambdaFunctionName,ParameterValue=AcmeRAGScanner \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Use Existing Guardrail

```bash
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
    ParameterKey=GuardrailId,ParameterValue=abc123xyz456 \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

---

## Cost Optimization

### Reduce Lambda Memory

Default: 512 MB. For small files, reduce to 256 MB:

```bash
aws lambda update-function-configuration \
  --function-name YOUR-LAMBDA-NAME \
  --memory-size 256 \
  --region us-east-1
```

### Enable S3 Intelligent-Tiering

For raw data bucket:

```bash
aws s3api put-bucket-intelligent-tiering-configuration \
  --bucket YOUR-RAW-BUCKET \
  --id EntireRawBucket \
  --intelligent-tiering-configuration '{
    "Id": "EntireRawBucket",
    "Status": "Enabled",
    "Tierings": [
      {"Days": 90, "AccessTier": "ARCHIVE_ACCESS"}
    ]
  }' \
  --region us-east-1
```

### Reduce CloudWatch Log Retention

Default: Never expire. Set to 7 days:

```bash
aws logs put-retention-policy \
  --log-group-name /aws/lambda/YOUR-LAMBDA-NAME \
  --retention-in-days 7 \
  --region us-east-1
```

---

## Security Hardening

### Enable S3 Versioning

```bash
aws s3api put-bucket-versioning \
  --bucket YOUR-RAW-BUCKET \
  --versioning-configuration Status=Enabled \
  --region us-east-1
```

### Enable S3 Access Logging

```bash
aws s3api put-bucket-logging \
  --bucket YOUR-RAW-BUCKET \
  --bucket-logging-status '{
    "LoggingEnabled": {
      "TargetBucket": "YOUR-LOGGING-BUCKET",
      "TargetPrefix": "raw-bucket-logs/"
    }
  }' \
  --region us-east-1
```

### Enable CloudTrail

```bash
aws cloudtrail create-trail \
  --name rag-shield-audit \
  --s3-bucket-name YOUR-CLOUDTRAIL-BUCKET \
  --region us-east-1
```

---

## Multi-Region Deployment

Deploy in multiple regions with unique bucket names:

```bash
# US East
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=RawDataBucketName,ParameterValue=acme-rag-raw-us-east \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
  --capabilities CAPABILITY_IAM \
  --region us-east-1

# EU West
aws cloudformation create-stack \
  --stack-name rag-shield \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=RawDataBucketName,ParameterValue=acme-rag-raw-eu-west \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
  --capabilities CAPABILITY_IAM \
  --region eu-west-1
```

---

## Environment-Specific Deployments

### Development

```bash
aws cloudformation create-stack \
  --stack-name rag-shield-dev \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=AlertEmail,ParameterValue=dev-team@company.com \
    ParameterKey=RawDataBucketName,ParameterValue=acme-rag-dev \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### Production

```bash
aws cloudformation create-stack \
  --stack-name rag-shield-prod \
  --template-body file://template.yaml \
  --parameters \
    ParameterKey=AlertEmail,ParameterValue=security@company.com \
    ParameterKey=RawDataBucketName,ParameterValue=acme-rag-prod \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```
