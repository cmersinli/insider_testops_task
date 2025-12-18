import os
import logging
import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


@pytest.fixture(autouse=True)
def captureScreenshotOnFailure(request, driver):
    yield
    if hasattr(request.node, "rep_call") and request.node.rep_call.failed:
        screenshotDir = "screenshots"
        os.makedirs(screenshotDir, exist_ok=True)
        screenshotPath = os.path.join(screenshotDir, f"failure_{request.node.name}.png")
        try:
            driver.save_screenshot(screenshotPath)
            logger.info(f"Screenshot saved: {screenshotPath}")
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")


@pytest.fixture(scope="class")
def driver():
    chromeOptions = Options()
    headlessMode = os.getenv("HEADLESS", "true").lower() == "true"
    remoteUrl = os.getenv("REMOTE_URL")

    if headlessMode:
        chromeOptions.add_argument("--headless")

    chromeOptions.add_argument("--no-sandbox")
    chromeOptions.add_argument("--disable-dev-shm-usage")
    chromeOptions.add_argument("--window-size=1920,1080")
    chromeOptions.add_argument("--disable-gpu")
    chromeOptions.add_argument("--disable-extensions")
    chromeOptions.add_argument("--disable-notifications")
    chromeOptions.add_argument("--disable-popup-blocking")

    if remoteUrl:
        logger.info(f"Creating Remote WebDriver: {remoteUrl}")
        browserDriver = webdriver.Remote(
            command_executor=remoteUrl,
            options=chromeOptions
        )
    else:
        logger.info("Creating Local Chrome WebDriver")
        browserDriver = webdriver.Chrome(options=chromeOptions)

    yield browserDriver

    logger.info("Quitting WebDriver")
    browserDriver.quit()
