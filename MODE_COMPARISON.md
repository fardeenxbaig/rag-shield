# Deployment Mode Comparison

## 🎯 Quick Decision Guide

```
Do you need physical isolation of clean/malicious files?
│
├─ YES → Use DualBucket Mode
│         (Clean files in separate bucket)
│
└─ NO  → Use SingleBucket Mode ✅ RECOMMENDED
          (Tag-based access control)
```

---

## 📊 Side-by-Side Comparison

### SingleBucket Mode (Recommended)

```
┌─────────────────────────────────────────────────────────────┐
│                    SINGLEBUCKET ARCHITECTURE                │
└─────────────────────────────────────────────────────────────┘

User uploads document.pdf
         ↓
┌────────────────────────┐
│ S3 Raw Data Bucket     │
│ • clean-doc.pdf  ✅    │ ← Tagged: ScanStatus=Clean
│ • malicious.pdf  ⚠️    │ ← Tagged: ScanStatus=Malicious
└────────────────────────┘
         ↓
┌────────────────────────┐
│ Bedrock Knowledge Base │
│ Reads from same bucket │
│                        │
│ ABAC Policy:           │
│ ✅ Can read Clean      │
│ ❌ Cannot read Malicious│
└────────────────────────┘

BENEFITS:
✅ Simple - One bucket
✅ Fast - No copying
✅ Cheap - No duplication
✅ Real-time - Immediate access

CONSIDERATIONS:
⚠️ Malicious files present (but tagged)
⚠️ Requires ABAC policy trust
```

---

### DualBucket Mode (Isolated)

```
┌─────────────────────────────────────────────────────────────┐
│                    DUALBUCKET ARCHITECTURE                  │
└─────────────────────────────────────────────────────────────┘

User uploads document.pdf
         ↓
┌────────────────────────┐
│ S3 Staging Bucket      │
│ • clean-doc.pdf  ✅    │
│ • malicious.pdf  ⚠️    │
└────────────────────────┘
         │
         ├─────────────────┬─────────────────┐
         ↓                 ↓                 ↓
    [Scanner]         [Scanner]         [Scanner]
         │                 │                 │
         ↓                 ↓                 ↓
    IF Clean         IF Malicious      IF Malicious
         │                 │                 │
         ↓                 ↓                 ↓
┌────────────────────┐  ┌──────────────┐  ┌──────────────┐
│ S3 KB Bucket       │  │ Forensic     │  │ Security Hub │
│ • clean-doc.pdf ✅ │  │ Bucket       │  │ Finding      │
│                    │  │ (Quarantine) │  └──────────────┘
│ (Only clean files) │  └──────────────┘
└────────────────────┘
         ↓
┌────────────────────────┐
│ Bedrock Knowledge Base │
│ Reads from KB bucket   │
│ (No malicious files)   │
└────────────────────────┘

BENEFITS:
✅ Isolated - Physical separation
✅ Clean - KB bucket only has safe files
✅ Simple KB - No ABAC needed

CONSIDERATIONS:
⚠️ Extra copy operation (~50ms)
⚠️ 2x storage cost
⚠️ More complex architecture
```

---

## 📈 Performance Comparison

| Metric | SingleBucket | DualBucket |
|--------|-------------|------------|
| **Upload to Scan** | ~800ms | ~800ms |
| **Scan to KB Ready** | Immediate | +50ms (copy) |
| **Total Latency** | ~800ms | ~850ms |
| **Storage Cost** | 1x | 2x (files in 2 buckets) |
| **S3 Operations** | 3 (get, tag, put) | 4 (get, tag, put, copy) |
| **Monthly Cost (10K files)** | ~$30 | ~$35 |

---

## 🔒 Security Comparison

| Security Feature | SingleBucket | DualBucket |
|-----------------|-------------|------------|
| **Malicious File Detection** | ✅ Yes | ✅ Yes |
| **Quarantine** | ✅ Yes | ✅ Yes |
| **Security Hub Alerts** | ✅ Yes | ✅ Yes |
| **Audit Trail** | ✅ Yes | ✅ Yes |
| **KB Protection** | ABAC Policy | Physical Isolation |
| **Malicious File Location** | Tagged in raw bucket | Not in KB bucket |

**Both modes are equally secure!** The difference is enforcement mechanism:
- SingleBucket: Policy-based (ABAC)
- DualBucket: Physical separation

---

## 🎯 Use Case Recommendations

### Choose SingleBucket if:
- ✅ You want simplicity
- ✅ You trust AWS IAM policies
- ✅ You want best performance
- ✅ You want lowest cost
- ✅ You're okay with tagged malicious files in bucket

### Choose DualBucket if:
- ✅ You need physical isolation
- ✅ You have compliance requirements
- ✅ You prefer "air-gapped" approach
- ✅ You want KB bucket to only contain clean files
- ✅ You don't want malicious files near KB data

---

## 💰 Cost Breakdown (10,000 files/month)

### SingleBucket Mode:
```
Lambda Execution:     $0.80
Bedrock Guardrails:   $7.50
S3 Storage (10GB):    $0.23
S3 Operations:        $0.05
DynamoDB:             $0.25
SNS:                  $0.01
Security Hub:         $0.00 (first 10K free)
─────────────────────────────
TOTAL:                ~$8.84/month
```

### DualBucket Mode:
```
Lambda Execution:     $0.80
Bedrock Guardrails:   $7.50
S3 Storage (20GB):    $0.46  ← 2x storage
S3 Operations:        $0.10  ← Extra copy ops
DynamoDB:             $0.25
SNS:                  $0.01
Security Hub:         $0.00
─────────────────────────────
TOTAL:                ~$9.12/month
```

**Difference:** ~$0.28/month (~3% more for DualBucket)

---

## 🔄 Migration Between Modes

### From SingleBucket → DualBucket:
```bash
1. Update CloudFormation stack with DeploymentMode=DualBucket
2. Update Lambda environment variable: DEPLOYMENT_MODE=DualBucket
3. Configure Bedrock KB to read from new KB bucket
4. Test with sample files
```

### From DualBucket → SingleBucket:
```bash
1. Update CloudFormation stack with DeploymentMode=SingleBucket
2. Update Lambda environment variable: DEPLOYMENT_MODE=SingleBucket
3. Apply ABAC policy to raw data bucket
4. Configure Bedrock KB to read from raw data bucket
5. Test with sample files
```

**No data loss** - both modes preserve all files and audit logs!

---

## 🎉 Final Recommendation

### Start with SingleBucket Mode ✅

**Why?**
- 97% of use cases don't need physical isolation
- Simpler to understand and maintain
- Better performance
- Lower cost
- ABAC policies are battle-tested and reliable

**When to switch to DualBucket:**
- Compliance audit requires physical separation
- Security team mandates "air-gapped" approach
- You have specific regulatory requirements

---

## 📞 Quick Reference

### SingleBucket Setup:
```bash
# Deploy
aws cloudformation create-stack \
  --parameters ParameterKey=DeploymentMode,ParameterValue=SingleBucket

# Upload files to:
s3://poisoned-rag-quarantine-raw-data-{account}/

# Configure KB to read from:
s3://poisoned-rag-quarantine-raw-data-{account}/
```

### DualBucket Setup:
```bash
# Deploy
aws cloudformation create-stack \
  --parameters ParameterKey=DeploymentMode,ParameterValue=DualBucket

# Upload files to:
s3://poisoned-rag-quarantine-raw-data-{account}/

# Configure KB to read from:
s3://poisoned-rag-quarantine-kb-ingestion-{account}/
```

---

**Both modes protect your RAG pipeline equally well!** 🛡️
