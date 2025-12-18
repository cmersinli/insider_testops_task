#!/usr/bin/env python3

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from typing import Callable, Any, Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("orchestrator")

NAMESPACE = os.getenv("NAMESPACE", "insider-testops")
CONTROLLER_POD_LABEL = os.getenv("CONTROLLER_POD_LABEL", "app=test-case-controller")
CHROME_NODE_POD_LABEL = os.getenv("CHROME_NODE_POD_LABEL", "app=chrome-node")
CHROME_NODE_HEADLESS_SVC = os.getenv("CHROME_NODE_HEADLESS_SVC", "chrome-node-headless")
KUBECONFIG = os.getenv("KUBECONFIG", None)
HELM_CHART_PATH = os.getenv("HELM_CHART_PATH", "./helm/insider-testops")
HELM_RELEASE_NAME = os.getenv("HELM_RELEASE_NAME", "insider-testops")
HELM_VALUES_FILE = os.getenv("HELM_VALUES_FILE", "")

READINESS_TIMEOUT = int(os.getenv("READINESS_TIMEOUT", "300"))
READINESS_CHECK_INTERVAL = int(os.getenv("READINESS_CHECK_INTERVAL", "5"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("RETRY_DELAY", "10"))

DEFAULT_NODE_COUNT = 1
MIN_NODE_COUNT = 1
MAX_NODE_COUNT = 5


class KubernetesOrchestrator:

    def __init__(self, kubeConfig: str = None):
        self._loadKubeConfig(kubeConfig or KUBECONFIG)
        self.coreV1Api = client.CoreV1Api()
        self.appsV1Api = client.AppsV1Api()
        self._collectedTestCases = []

    def _loadKubeConfig(self, kubeConfig: str = None) -> None:
        try:
            if kubeConfig:
                config.load_kube_config(config_file=kubeConfig)
                logger.info(f"Loaded kubeconfig from {kubeConfig}")
            else:
                try:
                    config.load_incluster_config()
                    logger.info("Loaded in-cluster config")
                except config.ConfigException:
                    config.load_kube_config()
                    logger.info("Loaded default kubeconfig")
        except Exception as e:
            logger.error(f"Failed to load kubeconfig: {e}")
            raise

    def _runCommand(self, command: list) -> tuple[int, str, str]:
        logger.debug(f"Running command: {' '.join(command)}")
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error("Command timed out")
            return 1, "", "Command timed out"
        except Exception as e:
            logger.error(f"Command failed: {e}")
            return 1, "", str(e)

    def _validateNodeCount(self, nodeCount: int) -> int:
        if nodeCount < MIN_NODE_COUNT:
            logger.warning(f"node_count {nodeCount} below minimum, using {MIN_NODE_COUNT}")
            return MIN_NODE_COUNT
        if nodeCount > MAX_NODE_COUNT:
            logger.warning(f"node_count {nodeCount} above maximum, using {MAX_NODE_COUNT}")
            return MAX_NODE_COUNT
        return nodeCount

    def _getPodsByLabel(self, labelSelector: str) -> list:
        try:
            pods = self.coreV1Api.list_namespaced_pod(
                namespace=NAMESPACE,
                label_selector=labelSelector
            )
            return pods.items
        except ApiException as e:
            logger.error(f"Failed to get pods with label {labelSelector}: {e}")
            return []

    def _getPodName(self, labelSelector: str) -> str:
        pods = self._getPodsByLabel(labelSelector)
        if pods:
            return pods[0].metadata.name
        return None

    def _isPodReady(self, pod) -> bool:
        if pod.status.phase != "Running":
            return False
        if not pod.status.container_statuses:
            return False
        return all(cs.ready for cs in pod.status.container_statuses)

    def _getChromeNodeDns(self, podName: str) -> str:
        return f"{podName}.{CHROME_NODE_HEADLESS_SVC}.{NAMESPACE}.svc.cluster.local"

    def _checkChromeNodeStatus(self, dnsName: str, controllerPodName: str, port: int = 4444) -> dict:
        url = f"http://{dnsName}:{port}/status"
        curlCommand = ["curl", "-s", "--connect-timeout", "3", url]

        try:
            returnCode, stdout, stderr = self._execInPod(controllerPodName, curlCommand)

            if returnCode != 0 or not stdout.strip():
                logger.debug(f"[_checkChromeNodeStatus] curl failed for {dnsName}: {stderr}")
                return {"available": False, "ready": False, "sessions": 0, "maxSessions": 0}

            data = json.loads(stdout)
            value = data.get("value", {})
            ready = value.get("ready", False)
            nodes = value.get("nodes", [])

            activeSessions = 0
            maxSessions = 1

            for node in nodes:
                slots = node.get("slots", [])
                maxSessions = len(slots)
                for slot in slots:
                    if slot.get("session") is not None:
                        activeSessions += 1

            available = ready and (activeSessions < maxSessions)

            return {
                "available": available,
                "ready": ready,
                "sessions": activeSessions,
                "maxSessions": maxSessions
            }
        except json.JSONDecodeError as e:
            logger.debug(f"[_checkChromeNodeStatus] JSON parse error for {dnsName}: {e}")
            return {"available": False, "ready": False, "sessions": 0, "maxSessions": 0}
        except Exception as e:
            logger.debug(f"[_checkChromeNodeStatus] Error for {dnsName}: {e}")
            return {"available": False, "ready": False, "sessions": 0, "maxSessions": 0}

    def _getAvailableChromeNode(self) -> Optional[str]:
        logger.info("[_getAvailableChromeNode] Searching for available Chrome Node...")

        controllerPodName = self._getPodName(CONTROLLER_POD_LABEL)
        if not controllerPodName:
            logger.error("[_getAvailableChromeNode] Test Controller Pod not found")
            return None

        logger.info(f"[_getAvailableChromeNode] Using Test Controller Pod: {controllerPodName}")

        pods = self._getPodsByLabel(CHROME_NODE_POD_LABEL)
        if not pods:
            logger.error("[_getAvailableChromeNode] No Chrome Node pods found")
            return None

        logger.info(f"[_getAvailableChromeNode] Found {len(pods)} Chrome Node pod(s)")

        for pod in pods:
            if not self._isPodReady(pod):
                logger.debug(f"[_getAvailableChromeNode] Pod {pod.metadata.name} not ready, skipping")
                continue

            dnsName = self._getChromeNodeDns(pod.metadata.name)
            status = self._checkChromeNodeStatus(dnsName, controllerPodName)

            logger.info(f"[_getAvailableChromeNode] {pod.metadata.name}: ready={status['ready']}, "
                       f"sessions={status['sessions']}/{status['maxSessions']}, available={status['available']}")

            if status["available"]:
                logger.info(f"[_getAvailableChromeNode] Selected: {dnsName}")
                return dnsName

        logger.warning("[_getAvailableChromeNode] No available Chrome Node found")
        return None

    def _execInPod(self, podName: str, command: list, container: str = None, envVars: dict = None) -> tuple[int, str, str]:
        logger.debug(f"Executing command in pod {podName}: {' '.join(command)}")

        try:
            if envVars:
                envPrefix = " ".join([f"{k}={v}" for k, v in envVars.items()])
                execCommand = ["/bin/sh", "-c", f"{envPrefix} {' '.join(command)}"]
            else:
                execCommand = ["/bin/sh", "-c", " ".join(command)]

            kwargs = {
                "name": podName,
                "namespace": NAMESPACE,
                "command": execCommand,
                "stderr": True,
                "stdin": False,
                "stdout": True,
                "tty": False,
                "_preload_content": False
            }

            if container:
                kwargs["container"] = container

            resp = stream(
                self.coreV1Api.connect_get_namespaced_pod_exec,
                **kwargs
            )

            stdout = ""
            stderr = ""

            while resp.is_open():
                resp.update(timeout=1)
                if resp.peek_stdout():
                    stdout += resp.read_stdout()
                if resp.peek_stderr():
                    stderr += resp.read_stderr()

            resp.close()
            returnCode = resp.returncode if hasattr(resp, "returncode") else 0

            return returnCode, stdout, stderr

        except ApiException as e:
            logger.error(f"API error executing command in pod {podName}: {e}")
            return 1, "", str(e)
        except Exception as e:
            logger.error(f"Error executing command in pod {podName}: {e}")
            return 1, "", str(e)

    def deploy(self, helmChartPath: str, nodeCount: int = DEFAULT_NODE_COUNT, valuesFile: str = None) -> bool:
        logger.info("[deploy] Starting Kubernetes resource deployment via Helm...")
        logger.info(f"[deploy] Helm chart path: {helmChartPath}")
        logger.info(f"[deploy] Release name: {HELM_RELEASE_NAME}")
        logger.info(f"[deploy] Namespace: {NAMESPACE}")

        nodeCount = self._validateNodeCount(nodeCount)
        logger.info(f"[deploy] Node count (HPA replicas): {nodeCount}")

        effectiveValuesFile = valuesFile or HELM_VALUES_FILE
        if effectiveValuesFile:
            logger.info(f"[deploy] Values file: {effectiveValuesFile}")

        if not os.path.exists(helmChartPath):
            logger.error(f"[deploy] Helm chart path does not exist: {helmChartPath}")
            return False

        helmCommand = [
            "helm", "upgrade", "--install",
            HELM_RELEASE_NAME,
            helmChartPath,
            "--namespace", NAMESPACE,
            "--create-namespace",
        ]

        if effectiveValuesFile and os.path.exists(effectiveValuesFile):
            helmCommand.extend(["-f", effectiveValuesFile])

        helmCommand.extend([
            "--set", f"chromeNode.replicaCount={nodeCount}",
            "--set", f"chromeNode.autoscaling.minReplicas={nodeCount}",
            "--set", f"chromeNode.autoscaling.maxReplicas={MAX_NODE_COUNT}",
            "--wait",
            "--timeout", "5m"
        ])

        logger.info(f"[deploy] Executing: {' '.join(helmCommand)}")

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[deploy] Attempt {attempt}/{MAX_RETRIES}")

            returnCode, stdout, stderr = self._runCommand(helmCommand)

            if stdout:
                logger.info("[deploy] Helm output:")
                for line in stdout.split("\n"):
                    if line.strip():
                        logger.info(f"  {line}")

            if returnCode == 0:
                logger.info("[deploy] SUCCESS - Helim deployment completed")
                return True

            logger.error(f"[deploy] Helm command failed with return codee: {returnCode}")
            if stderr:
                logger.error(f"[deploy] Stderr: {stderr}")

            if attempt < MAX_RETRIES:
                logger.info(f"[deploy] Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

        logger.error("[deploy] FAILED - All deployment attempts exhausted")
        return False

    def checkReadiness(self, labelSelector: str, minReady: int = 1) -> bool:
        logger.info(f"[checkReadiness] Waiting for pods with label '{labelSelector}' (min: {minReady})...")
        startTime = time.time()

        while time.time() - startTime < READINESS_TIMEOUT:
            pods = self._getPodsByLabel(labelSelector)
            readyCount = sum(1 for pod in pods if self._isPodReady(pod))

            logger.info(f"[checkReadiness] Pods ready: {readyCount}/{minReady} (total: {len(pods)})")

            if readyCount >= minReady:
                logger.info(f"[checkReadiness] SUCCESS - Required pods are ready ({readyCount}/{minReady})")
                return True

            time.sleep(READINESS_CHECK_INTERVAL)

        logger.error(f"[checkReadiness] TIMOUT after {READINESS_TIMEOUT}s")
        return False

    def passTestCases(self) -> list[str]:
        logger.info("[passTestCases] Collecting test cases from Test Case Controller Pod...")

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[passTestCases] Attempt {attempt}/{MAX_RETRIES}")

            controllerPodName = self._getPodName(CONTROLLER_POD_LABEL)
            if not controllerPodName:
                logger.warning("[passTestCases] Test Case Controller Pod not found")
                if attempt < MAX_RETRIES:
                    logger.info(f"[passTestCases] Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                logger.error("[passTestCases] FALED - Controller Pod not found after retries")
                return []

            logger.info(f"[passTestCases] Found Test Case Controller Pod: {controllerPodName}")

            returnCode, stdout, stderr = self._execInPod(
                controllerPodName,
                ["python", "-m", "pytest", "tests/", "--collect-only", "-q"]
            )

            testCases = []
            for line in stdout.split("\n"):
                line = line.strip()
                if line and "::" in line and not line.startswith(("=", "-", " ")):
                    testCases.append(line)

            if testCases:
                self._collectedTestCases = testCases
                logger.info(f"[passTestCases] SUCCESS - Collected {len(testCases)} test case(s)")
                for tc in testCases:
                    logger.info(f"[passTestCases]   - {tc}")
                return testCases

            if returnCode != 0:
                logger.warning(f"[passTestCases] Test collection returned non-zero: {returnCode}")
                if stderr:
                    logger.warning(f"[passTestCases] Stderr: {stderr}")

            if attempt < MAX_RETRIES:
                logger.info(f"[passTestCases] No tests collected, retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

        logger.warning("[passTestCases] No test cases collected after all retries")
        self._collectedTestCases = []
        return []

    def executeTests(self, testPath: str = "tests/", specificTests: list = None) -> tuple[bool, str]:
        logger.info("[executeTests] Executing tests in Test Controller Pod...")

        controllerPodName = self._getPodName(CONTROLLER_POD_LABEL)
        if not controllerPodName:
            logger.error("[executeTests] Test Controller Pod not found")
            return False, "Test Controller Pod not found"

        logger.info(f"[executeTests] Found Test Controller Pod: {controllerPodName}")

        availableNode = self._getAvailableChromeNode()
        if not availableNode:
            logger.error("[executeTests] No available Chrome Node found")
            return False, "No available Chrome Node"

        remoteUrl = f"http://{availableNode}:4444"
        logger.info(f"[executeTests] Using Chrome Node: {remoteUrl}")

        if specificTests:
            command = ["python", "-m", "pytest"] + specificTests + ["-v", "--tb=short", "-p", "no:cacheprovider"]
        else:
            command = ["python", "-m", "pytest", testPath, "-v", "--tb=short", "-p", "no:cacheprovider"]

        envVars = {
            "HEADLESS": "true",
            "REMOTE_URL": remoteUrl
        }
        logger.info(f"[executeTests] Environment: {envVars}")

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[executeTests] Attempt {attempt}/{MAX_RETRIES}")

            returnCode, stdout, stderr = self._execInPod(controllerPodName, command, envVars=envVars)

            logger.info("=" * 60)
            logger.info("[executeTests] TEST OUTPUT:")
            logger.info("=" * 60)
            for line in stdout.split("\n"):
                logger.info(line)
            if stderr:
                logger.info("-" * 60)
                logger.info("[executeTests] STDERR:")
                for line in stderr.split("\n"):
                    logger.info(line)
            logger.info("=" * 60)

            if returnCode == 0:
                logger.info("[executeTests] SUCCESS - Tests completed")
                return True, stdout

            if "passed" in stdout.lower() and "failed" not in stdout.lower():
                logger.info("[executeTests] SUCCESS - Tests passed (based on output)")
                return True, stdout

            logger.warning(f"[executeTests] Failed with return code: {returnCode}")

            if attempt < MAX_RETRIES:
                logger.info(f"[executeTests] Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

        logger.error("[executeTests] FAILED - All attempts exhausted")
        return False, stdout if stdout else stderr

    def handleErrors(
        self,
        operation: str,
        operationFunc: Callable[..., Any],
        *args,
        **kwargs
    ) -> tuple[bool, Optional[Any]]:
        logger.info(f"[handleErrors] Starting {operation} with retry support...")

        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[handleErrors] Attempt {attempt}/{MAX_RETRIES} for {operation}")

            try:
                result = operationFunc(*args, **kwargs)

                if isinstance(result, bool):
                    if result:
                        logger.info(f"[handleErrors] SUCCESS - {operation} completed")
                        return True, result
                    else:
                        raise Exception(f"{operation} returned False")

                if isinstance(result, tuple) and len(result) >= 1:
                    if result[0]:
                        logger.info(f"[handleErrors] SUCCESS - {operation} completed")
                        return True, result
                    else:
                        raise Exception(f"{operation} returned failure status")

                logger.info(f"[handleErrors] SUCCESS - {operation} completed")
                return True, result

            except Exception as e:
                logger.error(f"[handleErrors] Attempt {attempt} failed for {operation}: {e}")

                if attempt < MAX_RETRIES:
                    logger.info(f"[handleErrors] Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)

        logger.error(f"[handleErrors] FAILED - All {MAX_RETRIES} attempts exhausted for {operation}")
        return False, None

    def getPodStatus(self) -> dict:
        status = {
            "namespace": NAMESPACE,
            "testCaseController": [],
            "chromeNodes": []
        }

        controllerPods = self._getPodsByLabel(CONTROLLER_POD_LABEL)
        for pod in controllerPods:
            status["testCaseController"].append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": self._isPodReady(pod),
                "ip": pod.status.pod_ip
            })

        chromePods = self._getPodsByLabel(CHROME_NODE_POD_LABEL)
        for pod in chromePods:
            status["chromeNodes"].append({
                "name": pod.metadata.name,
                "phase": pod.status.phase,
                "ready": self._isPodReady(pod),
                "ip": pod.status.pod_ip
            })

        return status

    def run(self, helmChartPath: str = None, nodeCount: int = None, skipDeploy: bool = False, valuesFile: str = None) -> bool:
        effectiveNodeCount = nodeCount or DEFAULT_NODE_COUNT

        logger.info("=" * 60)
        logger.info("Kubernetes Selenium Test Orchestrator")
        logger.info("=" * 60)
        logger.info(f"Namespace: {NAMESPACE}")
        logger.info(f"Test Case Controller Label: {CONTROLLER_POD_LABEL}")
        logger.info(f"Chrome Node Label: {CHROME_NODE_POD_LABEL}")
        logger.info(f"Node Count (Chrome replicas): {effectiveNodeCount}")
        if valuesFile:
            logger.info(f"Values File: {valuesFile}")
        logger.info("=" * 60)

        if not skipDeploy and helmChartPath:
            logger.info("\n[STEP 1] deploy - Deploy K8s resources via Helm")
            success, _ = self.handleErrors(
                "deploy",
                self.deploy,
                helmChartPath,
                effectiveNodeCount,
                valuesFile
            )
            if not success:
                logger.error("Deployment failed after retries")
                return False
        else:
            logger.info("\n[STEP 1] deploy - SKIPPED (no helm chart path or --skip-deploy)")

        logger.info(f"\n[STEP 2] checkReadiness - Chrome Node Pod (minReady={effectiveNodeCount})")
        if not self.checkReadiness(CHROME_NODE_POD_LABEL, minReady=effectiveNodeCount):
            logger.error(f"Chrome Node Pod(s) did not become ready (expected {effectiveNodeCount})")
            return False

        logger.info("\n[STEP 3] checkReadiness - Test Case Controller Pod")
        if not self.checkReadiness(CONTROLLER_POD_LABEL, minReady=1):
            logger.error("Test Case Controller Pod did not become ready")
            return False

        status = self.getPodStatus()
        logger.info("\nPod Status:")
        logger.info(f"  Test Case Controller: {len(status['testCaseController'])} pod(s)")
        for pod in status["testCaseController"]:
            logger.info(f"    - {pod['name']}: {pod['phase']} (ready={pod['ready']}, ip={pod['ip']})")
        logger.info(f"  Chrome Nodes: {len(status['chromeNodes'])} pod(s)")
        for pod in status["chromeNodes"]:
            logger.info(f"    - {pod['name']}: {pod['phase']} (ready={pod['ready']}, ip={pod['ip']})")

        logger.info("\n[STEP 4] passTestCases - Collect from Test Case Controller")
        testCases = self.passTestCases()
        if not testCases:
            logger.warning("No test cases collected, will run all tests in tests/ directory")

        logger.info("\n[STEP 5] executeTests - Run in Chrome Node Pod")
        success, _ = self.executeTests()

        logger.info("\n" + "=" * 60)
        if success:
            logger.info("RESULT: TEST EXECUTION COMPLETED SUCCESSFULLY")
        else:
            logger.error("RESULT: TEST EXECUTION FAILED")
        logger.info("=" * 60)

        return success


def parseArgs():
    parser = argparse.ArgumentParser(
        description="Kubernetes Selenium Test Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  NAMESPACE              Kubernetes namespace (default: insider-testops)
  CONTROLLER_POD_LABEL   Label for Test Case Controller (default: app=test-case-controller)
  CHROME_NODE_POD_LABEL  Label for Chrome Node (default: app=chrome-node)
  KUBECONFIG             Path to kubeconfig file (default: auto-detect)
  HELM_CHART_PATH        Default Helm chart path (default: ./helm/insider-testops)
  HELM_RELEASE_NAME      Helm release name (default: insider-testops)
  HELM_VALUES_FILE       Helm values file path (default: none)
  READINESS_TIMEOUT      Pod readiness timeout in seconds (default: 300)
  MAX_RETRIES            Maximum retry attempts (default: 3)
  RETRY_DELAY            Delay between retries in seconds (default: 10)

Examples:
  %(prog)s --deploy --node-count 2
  %(prog)s --status
  %(prog)s --check-readiness
  %(prog)s --pass-test-cases
  %(prog)s --execute-tests
  %(prog)s --helm-chart-path ./helm/selenium-tests --node-count 3  # Full flow with deploy
        """
    )

    parser.add_argument(
        "--kubeconfig",
        type=str,
        default=None,
        help="Path to kubeconfig file (default: auto-detect)"
    )

    parser.add_argument(
        "--deploy",
        action="store_true",
        help="Deploy K8s resources via Helm (PDF 2.1)"
    )

    parser.add_argument(
        "--helm-chart-path",
        type=str,
        default=HELM_CHART_PATH,
        help=f"Path to Helm chart (default: {HELM_CHART_PATH})"
    )

    parser.add_argument(
        "--values-file", "-f",
        type=str,
        default=HELM_VALUES_FILE,
        help="Path to Helm values file (e.g., values-local.yaml)"
    )

    parser.add_argument(
        "--node-count",
        type=int,
        default=DEFAULT_NODE_COUNT,
        help=f"Number of Chrome Node replicas for HPA (min={MIN_NODE_COUNT}, max={MAX_NODE_COUNT}, default={DEFAULT_NODE_COUNT})"
    )

    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Skip deployment step in full run"
    )

    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current pod status and exit"
    )

    parser.add_argument(
        "--check-readiness",
        action="store_true",
        help="Only check pod readiness (PDF 2.3)"
    )

    parser.add_argument(
        "--pass-test-cases",
        action="store_true",
        help="Only collect and pass test cases (PDF 2.2)"
    )

    parser.add_argument(
        "--execute-tests",
        action="store_true",
        help="Only execute tests in Chrome Node (PDF 2.4)"
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    return parser.parse_args()


def main():
    args = parseArgs()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        orchestrator = KubernetesOrchestrator(kubeConfig=args.kubeconfig)

        if args.status:
            status = orchestrator.getPodStatus()
            print("\nPod Status:")
            print(f"  Namespace: {status['namespace']}")
            print(f"\n  Test Case Controller ({len(status['testCaseController'])} pods):")
            for pod in status["testCaseController"]:
                print(f"    - {pod['name']}: {pod['phase']} (ready={pod['ready']}, ip={pod['ip']})")
            print(f"\n  Chrome Nodes ({len(status['chromeNodes'])} pods):")
            for pod in status["chromeNodes"]:
                print(f"    - {pod['name']}: {pod['phase']} (ready={pod['ready']}, ip={pod['ip']})")
            sys.exit(0)

        if args.deploy:
            logger.info("Running: deploy")
            success = orchestrator.deploy(args.helm_chart_path, args.node_count, args.values_file)
            sys.exit(0 if success else 1)

        if args.check_readiness:
            logger.info("Running: checkReadiness")
            chromeReady = orchestrator.checkReadiness(CHROME_NODE_POD_LABEL)
            controllerReady = orchestrator.checkReadiness(CONTROLLER_POD_LABEL)
            success = chromeReady and controllerReady
            sys.exit(0 if success else 1)

        if args.pass_test_cases:
            logger.info("Running: passTestCases")
            testCases = orchestrator.passTestCases()
            print("\nCollected Test Cases:")
            for tc in testCases:
                print(f"  - {tc}")
            sys.exit(0 if testCases else 1)

        if args.execute_tests:
            logger.info("Running: executeTests")
            success, _ = orchestrator.executeTests()
            sys.exit(0 if success else 1)

        success = orchestrator.run(
            helmChartPath=args.helm_chart_path,
            nodeCount=args.node_count,
            skipDeploy=args.skip_deploy,
            valuesFile=args.values_file
        )
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
