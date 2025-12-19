# InsiderOne TestOps

Kubernetes-based Selenium test automation system. Runs tests on distributed Chrome nodes.

## Important Notes

> **Filter Fix:** The original case study document says Location filter should be `"Istanbul, Turkey"` but this doesnt work on the website. The actual filter value is `"Istanbul, Turkiye"` (with turkiye spelling). I fixed this in the test code.

> **AWS Free-Tier Change:** The case study mentions using `t2.micro` for EC2 but AWS free-tier rules seem to have changed. I had to use `t3.micro` instead becuase t2.micro wasnt availble in my region.

## Project Structure

```
insider_devops_task/
|-- tests/                          # selenium tests
|   |-- conftest.py                 # pytest fixtures
|   |-- test_insider.py             # test cases
|   |-- requirements.txt            # python dependancies
|   |-- pages/                      # page objects
|       |-- __init__.py
|       |-- base_page.py
|       |-- jobs_page.py
|       |-- open_positions_page.py
|-- docker/
|   |-- Dockerfile.controller       # test controller image
|   |-- Dockerfile.chrome-node      # chrome node image
|-- helm/insider-testops/           # kubernetes helm chart
|   |-- Chart.yaml
|   |-- values.yaml
|   |-- templates/
|       |-- deployment-controller.yaml
|       |-- statefulset-chrome-node.yaml
|       |-- service-chrome-node.yaml
|       |-- hpa.yaml
|       |-- rbac.yaml
|-- scripts/
|   |-- orchestrator.py             # test orchestration script
|   |-- requirements.txt
|-- terraform/                      # aws infrastructure
|   |-- main.tf
|   |-- variables.tf
|   |-- outputs.tf
|   |-- vpc.tf
|   |-- eks.tf
|   |-- ec2.tf
|   |-- ecr.tf
|   |-- iam.tf
|   |-- security-groups.tf
|-- screenshots/                    # kubectl outputs and test logs
    |-- kubectl_get_all.png
    |-- kubectl_get_deployment.png
    |-- kubectl_get_nodes.png
    |-- kubectl_get_pods.png
    |-- orchestrator-check-ready.png
    |-- orchestrator-execute-test.png
    |-- orchestrator-node-1.png
    |-- orchestrator-node-2.png
    |-- orchestrator-pass-test-case.png
```

## System Overview

The system consits of two seperate pods working together:

**Test Controller Pod** - Contains all test code, pytest framework and selenium client library. This pod discoveres and manages test cases. It doesnt have a browser installed, it just sends commands to Chrome Node.

**Chrome Node Pod** - Runs Selenium Server in standalone mode with Chrome browser. It recieves WebDriver commands from controller and executes them in headless Chrome. No test code here, just browser enviroment.

## How the Test Controller Pod Collects and Sends Tests to the Chrome Node Pod

The test collection and execution happends in two phases:

**Phase 1 - Test Collection:**
The orchestrator script runs `pytest --collect-only` inside the Controller pod. This command scans the test files and returns a list of all test cases without actualy running them. The controller knows what tests exist and can report this back.

**Phase 2 - Test Execution:**
When you run `--execute-tests`, the orchestrator triggers pytest inside the Controller pod. Pytest starts running tests and for each test that needs a browser, it creates a Remote WebDriver connection to Chrome Node using the `REMOTE_URL` enviroment variable (set to `http://chrome-node-service:4444`).

The selenium client in Controller pod sends HTTP requests to Chrome Node:
1. POST /session - creates new browser session
2. POST /session/{id}/url - navigates to webpage
3. POST /session/{id}/element - finds elements
4. POST /session/{id}/element/{id}/click - clicks on element
5. DELETE /session/{id} - closes browser when done

So basicly the Controller tells Chrome Node "open this page, click this button, check this text" and Chrome Node does the actual browser work and sends results back.

## How Inter-Pod Communication Works Between the Controller and Node

We use StatefulSet for Chrome Nodes with a headless Service. This gives each pod a stable DNS name that doesnt change:

```
chrome-node-0.chrome-node-service.insider-testops.svc.cluster.local:4444
chrome-node-1.chrome-node-service.insider-testops.svc.cluster.local:4444
chrome-node-2.chrome-node-service.insider-testops.svc.cluster.local:4444
```

The orchestrator script (running on your local machine) checks which Chrome Node is availble before sending tests. It querys each node's `/status` endpoint to see if its busy or free. When it finds a free node, it tells the Controller pod to use that specific node's DNS name.


This way we dont rely on random load balancing. The orchestrator knows exactly wich node is handling wich test, and can distribute tests across nodes effeciently.

## Steps to Deploy the System to Kubernetes

### Local Deployment (Kind)

For local develpoment we use Kind (Kubernetes IN Docker) instead of AWS. Its free and much faster to setup.

**Prerequisites:**
- Docker Desktop
- Kind (`brew install kind`)
- kubectl (`brew install kubectl`)
- Helm (`brew install helm`)
- Python 3.12

**Setup Steps:**

```bash
# 1. create kind cluster
kind create cluster --name insider-testops-cluster

# 2. build docker images
docker build -t insider-repo:test-case-controller-1.0.0 -f docker/Dockerfile.controller .
docker build -t insider-repo:chrome_node-142.0 -f docker/Dockerfile.chrome-node .

# 3. load images into kind (becuase kind cant pull from local registry)
kind load docker-image insider-repo:test-case-controller-1.0.0 --name insider-testops-cluster
kind load docker-image insider-repo:chrome_node-142.0 --name insider-testops-cluster

# 4. deploy to cluster
python scripts/orchestrator.py --deploy --node-count 3

# 5. run tests
python scripts/orchestrator.py --execute-tests
```

### AWS EKS Deployment

For production you deploy to Amazon EKS. You need an AWS account and terraform installed.

**Prerequisites:**
- AWS CLI configured with credentials
- Terraform installed
- kubectl installed

**Setup Steps:**

```bash
# 1. create aws infrastructure with terraform
cd terraform
terraform init
terraform apply
```

> **Note:** When EC2 instance is created, it automaticly clones the git repo and installs everthing needed. The terraform `user_data` script handles this:
> - Pulls `orchestrator.py` from repository
> - Pulls `helm/` charts from repository
> - Pulls all test code from repository
> - Installs kubectl, helm, python dependancies
>
> So when you SSH into EC2, **everthing is already there ready to use**. No manual setup required.

```bash
# 2. configure kubectl for eks
aws eks update-kubeconfig --region eu-west-1 --name insider-testops-cluster

# 3. login to ecr and push images
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.eu-west-1.amazonaws.com

docker build -t insider-repo:test-case-controller-1.0.0 -f docker/Dockerfile.controller .
docker tag insider-repo:test-case-controller-1.0.0 <account-id>.dkr.ecr.eu-west-1.amazonaws.com/insider-repo:test-case-controller-1.0.0
docker push <account-id>.dkr.ecr.eu-west-1.amazonaws.com/insider-repo:test-case-controller-1.0.0

docker build -t insider-repo:chrome_node-142.0 -f docker/Dockerfile.chrome-node .
docker tag insider-repo:chrome_node-142.0 <account-id>.dkr.ecr.eu-west-1.amazonaws.com/insider-repo:chrome_node-142.0
docker push <account-id>.dkr.ecr.eu-west-1.amazonaws.com/insider-repo:chrome_node-142.0

# 4. ssh into ec2 instance and run orchestrator
ssh -i your-key.pem ec2-user@<ec2-public-ip>

# 5. on ec2: deploy to eks
python scripts/orchestrator.py --deploy --node-count 3

# 6. on ec2: run tests
python scripts/orchestrator.py --execute-tests
```

## Orchestrator Commands

The python script handles test orchestration:

```bash
# deploy to cluster
python scripts/orchestrator.py --deploy --node-count 3

# run tests
python scripts/orchestrator.py --execute-tests

# check stauts
python scripts/orchestrator.py --status

# check pod readness before running tests
python scripts/orchestrator.py --check-readiness

# collect test cases (no execution)
python scripts/orchestrator.py --pass-test-cases
```
