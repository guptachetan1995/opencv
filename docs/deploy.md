# Deploying Second Look

Second Look ships as a single Lambda container image behind a Lambda Function URL
(SPEC §9): arm64, no ALB, nothing billing while idle, upgrading to S3-backed capture
storage later. **Deploying is a human-only action** (tracked as #47) — this document is
the runbook a person follows; nothing in this repo's automation runs any of these
commands for you.

**Status: attempted 2026-09-17, blocked — not a code or config problem.** The owner's
only available AWS account is a "Project" under AWS's Free Plan (Builder ID) product,
which sits inside an AWS-managed Organization the account holder cannot see or
administer (`settings.aws.com/projects`, management account ID `484394572314`). That
Organization's Service Control Policy explicitly denies resource creation for this
account, confirmed twice against the real account with the real IAM user this runbook
creates:

```
$ aws ecr create-repository --repository-name secondlook-lambda ...
An error occurred (AccessDeniedException) when calling the CreateRepository operation:
User: arn:aws:iam::461929939657:user/secondlook-deploy is not authorized to perform:
ecr:CreateRepository on resource: arn:aws:ecr:us-east-1:461929939657:repository/secondlook-lambda
with an explicit deny in a service control policy:
arn:aws:organizations::484394572314:policy/o-wihzhpc2xi/service_control_policy/p-5h3g8re9

$ aws lambda create-function --function-name secondlook --runtime python3.13 ...
An error occurred (AccessDeniedException) when calling the CreateFunction operation:
User: arn:aws:iam::461929939657:user/secondlook-deploy is not authorized to perform:
lambda:CreateFunction on resource: arn:aws:lambda:us-east-1:461929939657:function:secondlook
with an explicit deny in a service control policy:
arn:aws:organizations::484394572314:policy/o-wihzhpc2xi/service_control_policy/p-5h3g8re9
```

The second attempt ruled out "it's specific to container images": a Lambda `.zip`
deployment package was sized against the real pinned dependencies
(`opencv-python-headless==5.0.0.93` + `numpy==2.5.3`, the exact `manylinux_2_28_aarch64`
wheels this project's Docker image installs) — 140 MB unpacked, comfortably inside
Lambda's 250 MB unzipped ceiling — but `lambda:CreateFunction` itself is denied by the
identical policy, independent of packaging format. There is no packaging trick around
this; it is an account-tier guardrail, not a size or dependency problem.

Lifting it needs either activating AWS's "advanced features" on this account (per
AWS's own docs: irreversible, requires a paid upgrade first, and restructures the whole
organization that also hosts `alexa-plus`'s live EC2 deployment) or a separate,
unrestricted AWS account. Neither was available for this submission — no spare email
for a new account, and no budget for the upgrade. The owner decided to document this
honestly rather than pursue either. **This runbook is otherwise correct and complete**:
if an unrestricted AWS account becomes available later, every command below should work
unmodified.

## Prerequisites

- **Build step**: Docker (Engine or Desktop) with a version that supports
  `docker build --platform`. Nothing else — no AWS account, no credentials.
- **Deploy step** (owner-run only, #47): AWS CLI v2 and an AWS account with the
  permissions in [`deploy/iam-policy.json`](../deploy/iam-policy.json).

Run this locally, with no AWS credentials configured, to confirm the build step's
prerequisites:

```
docker --version
docker info --format '{{.Architecture}}/{{.OSType}}'
python3 --version
```

Real output captured in this environment (arm64-native host — `--platform linux/arm64`
needs no QEMU emulation here):

```
$ docker --version
Docker version 29.7.2, build a7dcaa6
$ docker info --format '{{.Architecture}}/{{.OSType}}'
aarch64/linux
$ python3 --version
Python 3.13.13
```

## Environment variables

None of these are ever hard-coded in any script — every one is read as `${VAR:-default}`.

| Variable | Used by | Default |
|---|---|---|
| `AWS_REGION` | `deploy.sh` | `us-east-1` |
| `AWS_PROFILE` | `deploy.sh` | `default` |
| `FUNCTION_NAME` | `deploy.sh` | `secondlook` |
| `ECR_REPOSITORY` | `deploy.sh` | `secondlook-lambda` |
| `IMAGE_TAG` | `build.sh`, `deploy.sh` | `secondlook-lambda:local` (`build.sh`) / build timestamp (`deploy.sh`) |
| `PLATFORM` | `build.sh` | `linux/arm64` |
| `TIMEOUT_SECONDS` | `deploy.sh` | `30` |
| `MEMORY_MB` | `deploy.sh` | `2048` (SPEC §9: above the 1,769 MB point where Lambda allocates a full vCPU — this pipeline is CPU-bound) |

If you override `FUNCTION_NAME` or `ECR_REPOSITORY` from their defaults, update the
matching resource ARNs in [`deploy/iam-policy.json`](../deploy/iam-policy.json) to
match — the policy's ARNs are pinned to the default names (`secondlook`,
`secondlook-lambda`), not derived from these variables.

## Step 1 — Build (local, no AWS credential needed)

```
cd entries/opencv
IMAGE_TAG=secondlook-lambda:local bash deploy/build.sh
```

Real captured output from this environment:

```
#0 building with "desktop-linux" instance using docker driver

#1 [internal] load remote build context
#1 DONE 0.0s

#2 copy /context /
#2 DONE 0.0s

#3 [internal] load metadata for public.ecr.aws/lambda/python:3.13
#3 DONE 1.8s

#4 [1/6] FROM public.ecr.aws/lambda/python:3.13@sha256:14e86df5b36acea7f8fbe101033b54be2f5a5ec7dea463d09177be1bf9e79bd1
#4 resolve public.ecr.aws/lambda/python:3.13@sha256:14e86df5b36acea7f8fbe101033b54be2f5a5ec7dea463d09177be1bf9e79bd1 done
#4 DONE 0.0s

#5 [2/6] COPY requirements.txt requirements.lock /var/task/
#5 CACHED

#6 [3/6] RUN pip install --require-hashes --no-cache-dir -r requirements.lock --target "/var/task"
#6 CACHED

#7 [4/6] COPY src/secondlook /var/task/secondlook
#7 CACHED

#8 [5/6] COPY app/static/review.html /var/task/static/review.html
#8 CACHED

#9 [6/6] COPY deploy/handler.py /var/task/handler.py
#9 DONE 0.0s

#10 exporting to image
#10 exporting layers 0.0s done
#10 exporting manifest sha256:44632210f8b3b058693a113f1e3d58ba366466e5435b58031aac8cceed30332f done
#10 exporting config sha256:5b9cf716d900f5801ed6c11a470abebb78ba8f3edb9eb50c24f57943cdde3562 done
#10 exporting attestation manifest sha256:8c11b006bc98f575d5489349afaa81aecaf403cd0933eca51c4c6c4eee74967b done
#10 exporting manifest list sha256:b2298e9303d6e2a822a4720f5127cba0989503c8b7a119f8a1ff6bf1a299495b done
#10 naming to docker.io/library/secondlook-lambda:local done
#10 unpacking to docker.io/library/secondlook-lambda:local
#10 unpacking to docker.io/library/secondlook-lambda:local 0.4s done
#10 DONE 0.5s
built secondlook-lambda:local for linux/arm64
```

The `pip install` and `COPY` layers show `CACHED` here because an identical layer was
already built locally in this environment during plan review; the image still exports
and tags successfully. A clean host with no prior build cache will show these layers
actually executing (`RUN pip install ...` printing real package-resolution output)
instead of `CACHED`, with the same final `built secondlook-lambda:local for
linux/arm64` line.

Confirms the target platform actually took effect:

```
$ docker image inspect secondlook-lambda:local --format '{{.Architecture}}'
arm64
```

## Step 2 — Local smoke check (recommended)

Docker-free, AWS-free: calls `handler.handler()` in-process against the committed
`data/synthetic/clean_a.jpg` sample.

```
cd entries/opencv
.venv/bin/python deploy/smoke_local.py
```

Real captured output:

```
GET /health -> {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': '{"status": "ok"}'}
POST /inspect -> verdict: {'outcome': 'accept', 'rule_id': 'accept', 'reason_code': 'clean', 'reason_text': 'Every measurement is comfortably inside its band.', 'hint_box': None, 'firings': [...], 'decided_by': 'policy'}
```

(`firings` is a full per-rule diagnostic list — truncated above for readability; the
real run prints every rule's matched/value/threshold triple.) Exit code `0`.

## Step 3 — Push and deploy (owner-run only, needs AWS credentials)

```
AWS_REGION=us-east-1 AWS_PROFILE=default bash deploy/deploy.sh
```

**Typical output, not executed in this environment (no AWS credentials configured
here); field values like account ID and ARNs will differ**:

```
Login Succeeded
[+] Building ...
built 123456789012.dkr.ecr.us-east-1.amazonaws.com/secondlook-lambda:20260908153000 for linux/arm64
The push refers to repository [123456789012.dkr.ecr.us-east-1.amazonaws.com/secondlook-lambda]
20260908153000: digest: sha256:... size: 1988
deployed secondlook; image 123456789012.dkr.ecr.us-east-1.amazonaws.com/secondlook-lambda:20260908153000
function url: https://abcdefghij1234567890.lambda-url.us-east-1.on.aws/
```

`deploy.sh` is idempotent — every AWS resource is checked before it's created, so
re-running it against an existing deployment only pushes a new image tag and updates
the function's code, without recreating the ECR repo, execution role, or Function URL.

## Step 4 — Verify the deployed URL

```
curl -s "$FUNCTION_URL/health"
# {"status": "ok"}

curl -s --data-binary @entries/opencv/data/synthetic/clean_a.jpg "$FUNCTION_URL/inspect"
# a verdict JSON, same shape as Step 2's captured output
```

**Warning**: concurrent requests during a demo can land on different, independently
started Lambda execution environments, each with its own in-memory `AgentLoop` — no
shared store exists yet (SPEC §9's `store.py` is unbuilt). A `GET /pending` right after
a `POST /inspect` is **not** guaranteed to see it if a different warm environment
handles the second request. Verify sequentially, one environment at a time, until
`store.py` lands.

## Rollback

Every pushed image tag stays in ECR until pruned, so rollback is just repointing the
function at a previous tag — no new resources needed.

```
aws ecr describe-images --repository-name "$ECR_REPOSITORY" \
  --query 'imageDetails[].imageTags'

aws lambda update-function-code --function-name "$FUNCTION_NAME" \
  --image-uri "<ecr_uri>:<previous-tag>"
```

(Typical output, not executed in this environment — no AWS credentials configured
here.)

## Cost

Function URLs cost nothing beyond the Lambda invocation itself — no ALB, no API
Gateway. At demo-scale traffic this stays inside AWS's Lambda Free Tier (SPEC §9).
The Function URL is created with `--auth-type NONE` (public, unauthenticated) so
judges can hit it directly without sharing AWS credentials — a deliberate,
documented tradeoff, not an oversight. The handler's existing 4 MB payload guard
(`MAX_BODY_BYTES` in `deploy/handler.py`) limits abuse somewhat; adding an AWS Budget
alarm is a named follow-up, not built here.

## Known limitations

- **In-memory state**: `AgentLoop` lives only for one warm Lambda execution
  environment's lifetime. No cross-invocation persistence exists until SPEC §9's
  `store.py` (S3-backed) is built.
- **Cold start**: unmeasured until a real deploy; SPEC estimates a few seconds cold,
  well under half a second warm.
- **`deploy/handler.py` is an interim stand-in** for SPEC §12's reserved
  `src/secondlook/handler.py`, which doesn't exist yet. When that module is built,
  its routes fold in from `deploy/handler.py` and `deploy/Dockerfile`'s `COPY`/`CMD`
  move to reference it, in the same PR.
