---
name: Process Issues
description: Workflow for finding, analyzing, and processing GitHub issues in the smart-charger project
category: workflow
tags:
  - github
  - issues
  - debugging
---

# Process Issues

Use this skill when analyzing error logs and creating GitHub issues.

## Find Issues

```bash
cd /Users/tobiast/Development/smart-charger && gh issue list

gh issue view <issue-number>
```

## Analyze Errors

1. **Identify**: Extract exception type and message
2. **Locate**: Find file and line from stack trace
3. **Understand**: Trace call flow to understand root cause
4. **Assess**: Determine impact on system

## Create Issue

```bash
gh issue create --title "<title>" --body "$(cat <<'EOF'
## Error

<error and stack trace>

### Location

<file:line>

### Root Cause

<why it happened>

### Suggested Fix

<proposed solution>
EOF
)"
```

## Example

Given:
```
AttributeError: 'NoneType' object has no attribute 'target_soc'
File "smartcharger.py", line 215
```

1. Read code at location
2. Understand why object is None
3. Create issue with full analysis