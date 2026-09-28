# Deploying Second Look

Two AWS paths serve the same routes (`src/secondlook/service.py`): a Lambda container image
behind a Function URL, and one EC2 instance running `app/server.py`. **Deploying is a
human-only action** — this document is the runbook a person follows; nothing in this repo's
automation deploys anything.

| Path | State |
|---|---|
| Lambda + Function URL (`deploy/deploy.sh`) | **Blocked**: attempted 2026-09-17 in `us-east-1`; the account's Organization Service Control Policy denies `ecr:CreateRepository` and `lambda:CreateFunction`. |
| EC2 console deploy (`deploy/ec2/`) | **Prepared, not launched.** Every console field is below; the owner reviews them and clicks Launch. |

Until one of them serves, a live screen-share of the running local server (`make run`,
`tools/run_demo.py`, the review page) is available to judges on request via a Devpost message.

## EC2 console deploy

One `t3.micro` running the EC2 image (`deploy/ec2/Dockerfile`: `app/server.py` on
`python:3.13-slim`), built on first boot by `deploy/ec2/user-data.sh` from the **public**
repository, serving plain HTTP on port 80. It is the same route table as `make run`, with the
reviewer routes behind a token generated on the instance.

**Why EC2, and why this region.** The Lambda path is denied by the account's policy (below).
Another project in the same AWS organization was deployed to EC2 through the console on
2026-09-11, in `ap-southeast-2`, after `us-east-1` turned out to be blocked by an Organizations
policy for it too — so `ap-southeast-2` is the one region this account has been seen to allow.
Whether this account's policy also allows EC2 there is only settled by trying; if the launch is
refused, record the console's error message in this file.

**Before launching:** the public repository must already hold this version (the instance
clones `main` of `github.com/guptachetan1995/opencv` at boot), and the owner has given a
go-ahead in chat for this specific launch.

### The fields (EC2 console > Instances > Launch instances)

| Field | Value |
|---|---|
| Region (top-right selector) | **Asia Pacific (Sydney) `ap-southeast-2`** |
| Name and tags > Name | `secondlook-demo` |
| Application and OS Images | **Amazon Linux 2023 AMI** (Quick Start; 64-bit **x86**) |
| Instance type | **`t3.micro`** (marked "Free tier eligible") |
| Key pair (login) | **Proceed without a key pair** — nothing on the instance needs a login |
| Network settings > VPC / Subnet | the default VPC, "No preference" |
| Network settings > Auto-assign public IP | **Enable** |
| Firewall (security groups) | **Create security group**; name `secondlook-demo-sg`; description `Second Look demo: HTTP only` |
| Security group rules | **Untick** "Allow SSH traffic from"; **tick** "Allow HTTP traffic from the internet" (TCP 80 from 0.0.0.0/0); leave HTTPS unticked (there is no certificate) |
| Configure storage | the default: 1 × 8 GiB gp3 root volume |
| Advanced details > Metadata version | **V2 only (token required)** |
| Advanced details > User data | the whole of [`deploy/ec2/user-data.sh`](../deploy/ec2/user-data.sh), pasted as text ("already base64-encoded" unticked) |
| Summary > Number of instances | 1 |

The owner reviews the summary panel against this table and clicks **Launch instance**. The
agent filling the form never clicks it.

### What the boot script does

`user-data.sh` runs once as root: `dnf install -y docker git`, starts Docker, clones the public
repository to `/opt/secondlook`, builds `deploy/ec2/Dockerfile`, generates a 32-hex-character
reviewer token with Python's `secrets` module into a root-only file, and runs the container
with `--restart unless-stopped -p 80:8080 -e REVIEWER_TOKEN=…`. The token never appears in the
script, the console form or the repository; the script prints it once to the instance's system
log. First boot takes a few minutes (the image build downloads the pinned wheels).

### After launch

1. **Public address:** the instance's "Public IPv4 address" (or public DNS) on its details
   page. The URL is `http://<public-ip>/`.
2. **The reviewer token:** Instance > Actions > Monitor and troubleshoot > **Get system log**;
   the line `second-look reviewer token: …` (the log can take a few minutes to appear). Keep it
   out of any published text.
3. **Verify** from the repository root, and paste the real output into this section. Run it
   first, on the fresh instance, before step 4 or anyone else posts a photo: capture ids are
   assigned in arrival order, so on a used instance `c_001`/`c_002` name other captures and the
   retake line fails.

   ```sh
   BASE=http://<public-ip>
   curl -s -w '\n' "$BASE/health"
   curl -s -X POST --data-binary @data/synthetic/glare_text.jpg "$BASE/inspect" \
     | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); v=d["verdict"]; print(d["capture_id"], d["state"], v["rule_id"], v["hint_box"], "successor:", d["successor_id"])'
   curl -s -X POST --data-binary @data/synthetic/crop_bottom.jpg "$BASE/retake/c_002" \
     | .venv/bin/python -c 'import json,sys; d=json.load(sys.stdin); print(d["capture_id"], d["state"], d["verdict"]["rule_id"])'
   curl -s -w ' %{http_code}\n' -X POST -d '{}' "$BASE/approve/c_001"
   curl -s -o /dev/null -w '%{time_total}s\n' "$BASE/health"
   ```

   Expected: `{"status": "ok"}`, then `c_001 awaiting_retake glare_over_total [201, 1006, 462,
   141] successor: c_002`, then `c_002 awaiting_retake bottom_edge_clipped`, then
   `{"error": "reviewer token required"} 401`, then the round-trip time (informational only).
4. Open `$BASE/` in a browser, paste the token, and check that a posted `not_doc.jpg` shows its
   overlay and can be rejected.
5. Then, and only then: add the URL to the README's Deployment section and the Devpost "Try it
   out" links, and redraw the architecture diagram's AWS band with the EC2 node solid.

### Exposure, cost and teardown

- **What is public:** anyone with the URL can post a photo, read `/pending`, `/capture/<id>`
  and `/trace/<id>` (measurements and verdicts, never pixels), and open the review page.
  Approve, reject, resolve-duplicate and the photo overlay need the reviewer token. An
  escalated photo is held on the instance until it is decided (at most 64, oldest deleted
  first). Judges should post the committed synthetic samples, not real receipts.
- **Plain HTTP:** there is no certificate, so the token protects the reviewer routes from
  casual callers, not from someone observing the network between the reviewer and the
  instance.
- **State is in memory:** a container restart empties the batch.
- **Cost:** `t3.micro` is free-tier eligible; AWS also bills public IPv4 addresses hourly. The
  account is on AWS's Free Plan; check the Billing console that the instance is covered. Any
  cost beyond that is the owner's decision.
- **Teardown** after judging: terminate `secondlook-demo`, then delete `secondlook-demo-sg`.

## Lambda + Function URL

The designed target: one AWS Lambda function, packaged as a container image on arm64
(Graviton2), 2048 MB, Python 3.13, behind a Lambda Function URL — no ALB, nothing billing while
idle, upgrading to S3-backed capture storage later.

**Status: attempted 2026-09-17, blocked — not a code or config problem.** The owner's only
available AWS account is a "Project" under AWS's Free Plan (Builder ID) product, which sits
inside an AWS-managed Organization the account holder cannot see or administer
(`settings.aws.com/projects`). That Organization's Service Control Policy explicitly denies
resource creation for this account, confirmed twice against the real account with the real IAM
user this runbook creates (account ids replaced with `<account>` and `<management-account>`):

```
$ aws ecr create-repository --repository-name secondlook-lambda ...
An error occurred (AccessDeniedException) when calling the CreateRepository operation:
User: arn:aws:iam::<account>:user/secondlook-deploy is not authorized to perform:
ecr:CreateRepository on resource: arn:aws:ecr:us-east-1:<account>:repository/secondlook-lambda
with an explicit deny in a service control policy:
arn:aws:organizations::<management-account>:policy/o-wihzhpc2xi/service_control_policy/p-5h3g8re9

$ aws lambda create-function --function-name secondlook --runtime python3.13 ...
An error occurred (AccessDeniedException) when calling the CreateFunction operation:
User: arn:aws:iam::<account>:user/secondlook-deploy is not authorized to perform:
lambda:CreateFunction on resource: arn:aws:lambda:us-east-1:<account>:function:secondlook
with an explicit deny in a service control policy:
arn:aws:organizations::<management-account>:policy/o-wihzhpc2xi/service_control_policy/p-5h3g8re9
```

The second attempt ruled out "it's specific to container images": a Lambda `.zip`
deployment package was sized against the real pinned dependencies
(`opencv-python-headless==5.0.0.93` + `numpy==2.5.3`, the exact `manylinux_2_28_aarch64`
wheels this project's Docker image installs) — 140 MB unpacked, comfortably inside
Lambda's 250 MB unzipped ceiling — but `lambda:CreateFunction` itself is denied by the
identical policy, independent of packaging format. Both attempts were in `us-east-1`; a retry
in `ap-southeast-2` has not been made.

Lifting the policy needs either activating AWS's "advanced features" on this account (per
AWS's own docs: irreversible, requires a paid upgrade first, and restructures the whole
organization, which also hosts another project's live deployment) or a separate,
unrestricted AWS account. Neither was available for this submission — no spare email
for a new account, and no budget for the upgrade. The owner decided to document this
honestly rather than pursue either. **This runbook is otherwise correct and complete**:
if an unrestricted AWS account becomes available later, every command below should work
unmodified.

### Prerequisites

- **Build step**: Docker (Engine or Desktop) with a version that supports
  `docker build --platform`. Nothing else — no AWS account, no credentials.
- **Deploy step** (owner-run only): AWS CLI v2 and an AWS account with the
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

### Environment variables

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
| `MEMORY_MB` | `deploy.sh` | `2048` (above the 1,769 MB point where Lambda allocates a full vCPU — this pipeline is CPU-bound) |
| `REVIEWER_TOKEN` | `deploy.sh` (required, no default), then the function's environment | none — `deploy.sh` stops if it is unset, because the Function URL is public and the reviewer routes need it |

If you override `FUNCTION_NAME` or `ECR_REPOSITORY` from their defaults, update the
matching resource ARNs in [`deploy/iam-policy.json`](../deploy/iam-policy.json) to
match — the policy's ARNs are pinned to the default names (`secondlook`,
`secondlook-lambda`), not derived from these variables.

### Step 1 — Build (local, no AWS credential needed)

```
# from the repository root
IMAGE_TAG=secondlook-lambda:local bash deploy/build.sh
```

Real captured output from this environment, on 2026-09-17 (before `service.py` and
`overlay.py` existed; the image copies all of `src/secondlook`, so they ride along unchanged):

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
and tags successfully.

Confirms the target platform actually took effect:

```
$ docker image inspect secondlook-lambda:local --format '{{.Architecture}}'
arm64
```

### Step 2 — Local smoke check (recommended)

Docker-free, AWS-free: calls `handler.handler()` in-process against the committed
`data/synthetic/clean_a.jpg` sample.

```
# from the repository root, after make setup
.venv/bin/python deploy/smoke_local.py
```

Real captured output (2026-09-28):

```
GET /health -> {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': '{"status": "ok"}', 'isBase64Encoded': False}
POST /inspect -> verdict: {'outcome': 'accept', 'rule_id': 'accept', 'reason_code': 'clean', 'reason_text': 'Every measurement is comfortably inside its band.', 'hint_box': None, 'firings': [...], 'decided_by': 'policy'}
```

(`firings` is a full per-rule diagnostic list — truncated above for readability; the
real run prints every rule's matched/value/threshold triple.) Exit code `0`.

### Step 3 — Push and deploy (owner-run only, needs AWS credentials)

```
AWS_REGION=us-east-1 AWS_PROFILE=default REVIEWER_TOKEN=<a long random secret> bash deploy/deploy.sh
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
the function's code and its `REVIEWER_TOKEN`, without recreating the ECR repo, execution
role, or Function URL.

### Step 4 — Verify the deployed URL

```
curl -s "$FUNCTION_URL/health"
# {"status": "ok"}

curl -s --data-binary @data/synthetic/clean_a.jpg "$FUNCTION_URL/inspect"
# a verdict JSON, same shape as Step 2's captured output
```

**Warning**: concurrent requests during a demo can land on different, independently
started Lambda execution environments, each with its own in-memory `AgentLoop` — no
shared store exists yet (the S3-backed `store.py` is not built). A `GET /pending` right after
a `POST /inspect` is **not** guaranteed to see it if a different warm environment
handles the second request. Verify sequentially, one environment at a time, until
`store.py` lands. (The EC2 path has one process and no such split.)

### Rollback

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

### Cost and exposure

Function URLs cost nothing beyond the Lambda invocation itself — no ALB, no API
Gateway. At demo-scale traffic this stays inside AWS's Lambda free tier ("one million
requests and 400,000 GB-seconds per month", from <https://aws.amazon.com/lambda/pricing/>).
The Function URL is created with `--auth-type NONE` so judges can call it without AWS
credentials. That no longer exposes the human gate: approve, reject, resolve-duplicate and the
photo overlay answer `401` without the reviewer token, which `deploy.sh` sets as the function's
`REVIEWER_TOKEN`. What stays public is posting a photo and reading measurements and traces. The
4 MB payload guard (`MAX_BODY_BYTES` in `src/secondlook/service.py`) limits abuse somewhat;
adding an AWS Budget alarm is a named follow-up, not built here.

## Known limitations

- **In-memory state**: `AgentLoop` lives only for one process (EC2) or one warm Lambda
  execution environment. No persistence exists until the planned S3-backed `store.py` is built.
- **Cold start**: unmeasured until a real deploy; the design estimate for a roughly
  300–400 MB OpenCV container image is a few seconds cold, well under half a second warm.
- **`deploy/handler.py` is the Lambda adapter**, a thin translation onto
  `src/secondlook/service.py`; a planned `src/secondlook/handler.py` would only move it.
- **The EC2 image has not been built yet**: its first build is the instance's first boot.
  Docker was not running on the machine this was prepared on, so the verification output
  above is what establishes that it works.
