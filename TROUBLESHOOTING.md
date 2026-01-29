# Troubleshooting Guide

## Common Issues

### Issue: Files Not Being Scanned

**Symptoms:**
- Upload files but no `ScanStatus` tag appears
- No Lambda invocations

**Diagnosis:**
```bash
# Check EventBridge rule
aws events list-rules --name-prefix rag-shield --region us-east-1

# Check Lambda recent invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=YOUR-LAMBDA-NAME \
  --start-time $(date -u -d '10 minutes ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Sum \
  --region us-east-1
```

**Solutions:**
1. **EventBridge rule disabled** → Enable in AWS Console
2. **Lambda errors** → Check CloudWatch logs
3. **IAM permissions missing** → Verify Lambda execution role

---

### Issue: All Files Tagged as Clean (False Negatives)

**Symptoms:**
- Known malicious files are tagged as `Clean`
- Guardrail not detecting threats

**Diagnosis:**
```bash
# Check Guardrail configuration
GUARDRAIL_ID=$(aws cloudformation describe-stacks \
  --stack-name rag-shield \
  --query 'Stacks[0].Parameters[?ParameterKey==`GuardrailId`].ParameterValue' \
  --output text)

aws bedrock get-guardrail \
  --guardrail-identifier $GUARDRAIL_ID \
  --region us-east-1
```

**Solutions:**
1. Verify Guardrail has `PROMPT_ATTACK` filter enabled
2. Check filter strength is set to `HIGH`
3. Test with known malicious content

---

### Issue: No Email Alerts

**Symptoms:**
- Malicious files detected but no email sent
- SNS subscription not confirmed

**Diagnosis:**
```bash
# Check SNS subscription status
TOPIC_ARN=$(aws cloudformation describe-stacks \
  --stack-name rag-shield \
  --query 'Stacks[0].Outputs[?OutputKey==`SNSTopicArn`].OutputValue' \
  --output text)

aws sns list-subscriptions-by-topic \
  --topic-arn $TOPIC_ARN \
  --region us-east-1
```

**Expected:** Subscription with `SubscriptionArn` (not "PendingConfirmation")

**Solutions:**
1. Check spam folder for confirmation email
2. Resend confirmation:
   ```bash
   aws sns subscribe \
     --topic-arn $TOPIC_ARN \
     --protocol email \
     --notification-endpoint your-email@company.com \
     --region us-east-1
   ```
3. Confirm subscription via email link

---

### Issue: Stack Creation Fails

**Symptoms:**
- Stack status shows `ROLLBACK_COMPLETE`
- Resources not created

**Diagnosis:**
```bash
# View failure reason
aws cloudformation describe-stack-events \
  --stack-name rag-shield \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].{Resource:LogicalResourceId,Reason:ResourceStatusReason}' \
  --output table \
  --region us-east-1
```

**Common Failures:**

1. **"Bucket name already exists"**
   - S3 bucket names are globally unique
   - Solution: Use custom bucket name parameter

2. **"Insufficient permissions"**
   - Your IAM user/role lacks permissions
   - Solution: Ensure you have CloudFormation, Lambda, S3, DynamoDB, IAM, Bedrock permissions

3. **"Bedrock not available in region"**
   - Bedrock Guardrails not available in all regions
   - Solution: Deploy in us-east-1, us-west-2, or eu-west-1

---

### Issue: Lambda Errors in Logs

**Symptoms:**
- Files uploaded but Lambda fails
- Error messages in CloudWatch

**Diagnosis:**
```bash
# View Lambda logs
aws logs tail /aws/lambda/YOUR-LAMBDA-NAME \
  --since 10m \
  --filter-pattern "ERROR" \
  --region us-east-1
```

**Common Errors:**

1. **"AccessDenied" on S3**
   - Lambda role missing S3 permissions
   - Solution: Verify IAM role has `s3:GetObject`, `s3:PutObjectTagging`

2. **"AccessDenied" on Bedrock**
   - Lambda role missing Bedrock permissions
   - Solution: Verify IAM role has `bedrock:ApplyGuardrail`

3. **"GuardrailNotFoundException"**
   - Guardrail ID invalid or deleted
   - Solution: Check Guardrail exists in Bedrock console

---

### Issue: Bedrock KB Still Reading Malicious Files

**Symptoms:**
- KB returns content from files tagged as `Malicious`
- ABAC policy not working (SingleBucket mode)

**Diagnosis:**
```bash
# Verify KB IAM role has ABAC condition
aws iam get-role-policy \
  --role-name YOUR-KB-ROLE-NAME \
  --policy-name S3AccessPolicy \
  --region us-east-1
```

**Required Condition:**
```json
"Condition": {
  "StringEquals": {
    "s3:ExistingObjectTag/ScanStatus": "Clean"
  }
}
```

**Solution:**
Update KB IAM role policy to include ABAC condition.

---

### Issue: DualBucket - Files Not Copied to KB Bucket

**Symptoms:**
- Clean files stay in raw bucket
- KB bucket remains empty

**Diagnosis:**
```bash
# Check Lambda environment variables
aws lambda get-function-configuration \
  --function-name YOUR-LAMBDA-NAME \
  --query 'Environment.Variables' \
  --region us-east-1
```

**Expected:**
- `DEPLOYMENT_MODE=DualBucket`
- `KB_INGESTION_BUCKET=your-kb-bucket-name`

**Solution:**
Verify stack was deployed with `DeploymentMode=DualBucket` parameter.

---

### Issue: Forensic Bucket Cannot Be Deleted

**Symptoms:**
- Cannot delete forensic bucket during cleanup
- "Object Lock" error

**Cause:**
Object Lock enabled with 90-day retention

**Solutions:**

1. **Wait 90 days** for retention to expire

2. **Delete with GOVERNANCE bypass** (if you have permission):
   ```bash
   aws s3api delete-object \
     --bucket YOUR-FORENSIC-BUCKET \
     --key quarantine/2026/01/29/SCAN-ID/file.txt \
     --bypass-governance-retention \
     --region us-east-1
   ```

3. **Contact AWS Support** to disable Object Lock

---

## Debugging Commands

### Check Stack Status

```bash
aws cloudformation describe-stacks \
  --stack-name rag-shield \
  --query 'Stacks[0].StackStatus' \
  --output text \
  --region us-east-1
```

### View All Stack Resources

```bash
aws cloudformation describe-stack-resources \
  --stack-name rag-shield \
  --region us-east-1
```

### Test Lambda Manually

```bash
aws lambda invoke \
  --function-name YOUR-LAMBDA-NAME \
  --payload '{"detail":{"bucket":{"name":"YOUR-BUCKET"},"object":{"key":"test.txt"}}}' \
  response.json \
  --region us-east-1

cat response.json
```

### View Recent Lambda Errors

```bash
aws logs tail /aws/lambda/YOUR-LAMBDA-NAME \
  --since 1h \
  --filter-pattern "ERROR" \
  --region us-east-1
```

### Check DynamoDB Audit Logs

```bash
aws dynamodb scan \
  --table-name YOUR-AUDIT-TABLE \
  --region us-east-1 \
  --max-items 10
```

---

## Getting Help

If you're still stuck:

1. **Check CloudWatch Logs** - Most errors are logged there
2. **Review Stack Events** - Shows why resources failed to create
3. **Open GitHub Issue** - Include error messages and stack events
4. **AWS Support** - For AWS service-specific issues

---

## Useful Links

- [AWS CloudFormation Documentation](https://docs.aws.amazon.com/cloudformation/)
- [Amazon Bedrock Guardrails Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- [AWS Lambda Troubleshooting](https://docs.aws.amazon.com/lambda/latest/dg/lambda-troubleshooting.html)
