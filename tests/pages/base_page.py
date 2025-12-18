import logging
from functools import wraps
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    ElementClickInterceptedException
)

logger = logging.getLogger(__name__)


def retryOnStaleElement(maxAttempts: int = 3, delay: float = 0.5):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            for attempt in range(maxAttempts):
                try:
                    return func(*args, **kwargs)
                except StaleElementReferenceException:
                    logger.warning(f"Stale element on attempt {attempt + 1}/{maxAttempts} in {func.__name__}")
                    if attempt == maxAttempts - 1:
                        raise
                    time.sleep(delay)
        return wrapper
    return decorator


class BasePage:

    DEFAULT_TIMEOUT = 20
    SHORT_TIMEOUT = 5
    LONG_TIMEOUT = 30

    # COOKIE_ACCEPT = (By.ID, "wt-cli-accept-all-btn")
    COOKIE_ACCEPT = (By.XPATH, "//a[text()='Accept All']")

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, self.DEFAULT_TIMEOUT)

    def open(self, url: str) -> None:
        logger.info(f"Opening URL: {url}")
        self.driver.get(url)

    def findElement(self, locator: tuple, timeout: int = None) -> WebElement:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, waitTime).until(
            EC.presence_of_element_located(locator)
        )

    def findElements(self, locator: tuple, timeout: int = None) -> list[WebElement]:
        waitTime = timeout or self.SHORT_TIMEOUT
        try:
            WebDriverWait(self.driver, waitTime).until(
                EC.presence_of_element_located(locator)
            )
        except TimeoutException:
            return []
        return self.driver.find_elements(*locator)

    def click(self, locator: tuple, timeout: int = None) -> None:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        element = WebDriverWait(self.driver, waitTime).until(
            EC.element_to_be_clickable(locator)
        )
        element.click()

    def clickWithJs(self, locator: tuple, timeout: int = None) -> None:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        element = WebDriverWait(self.driver, waitTime).until(
            EC.presence_of_element_located(locator)
        )
        self.driver.execute_script("arguments[0].click();", element)

    def isElementVisible(self, locator: tuple, timeout: int = None) -> bool:
        waitTime = timeout or self.SHORT_TIMEOUT
        try:
            WebDriverWait(self.driver, waitTime).until(
                EC.visibility_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    def waitForElementClickable(self, locator: tuple, timeout: int = None) -> WebElement:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, waitTime).until(
            EC.element_to_be_clickable(locator)
        )

    def waitForElementVisible(self, locator: tuple, timeout: int = None) -> WebElement:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, waitTime).until(
            EC.visibility_of_element_located(locator)
        )

    def waitForElementInvisible(self, locator: tuple, timeout: int = None) -> bool:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, waitTime).until(
            EC.invisibility_of_element_located(locator)
        )

    def waitForUrlContains(self, urlPart: str, timeout: int = None) -> bool:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        return WebDriverWait(self.driver, waitTime).until(
            EC.url_contains(urlPart)
        )

    def waitForSelectOptionsLoaded(self, locator: tuple, minOptions: int = 2, timeout: int = None) -> bool:
        waitTime = timeout or self.LONG_TIMEOUT

        def optionsLoaded(driver):
            try:
                element = driver.find_element(*locator)
                selectObj = Select(element)
                return len(selectObj.options) >= minOptions
            except (NoSuchElementException, StaleElementReferenceException):
                return False

        try:
            return WebDriverWait(self.driver, waitTime).until(optionsLoaded)
        except TimeoutException:
            logger.warning(f"Timeout waiting for select options to load: {locator}")
            return False

    def getText(self, locator: tuple) -> str:
        return self.findElement(locator).text

    def scrollToElement(self, locator: tuple) -> None:
        element = self.findElement(locator)
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

    def scrollToWebElement(self, element: WebElement) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

    def getCurrentUrl(self) -> str:
        return self.driver.current_url

    def switchToNewTab(self) -> None:
        windowHandles = self.driver.window_handles
        self.driver.switch_to.window(windowHandles[-1])

    def waitForNewWindow(self, expectedWindowCount: int = 2, timeout: int = None) -> bool:
        waitTime = timeout or self.DEFAULT_TIMEOUT
        try:
            return WebDriverWait(self.driver, waitTime).until(
                EC.number_of_windows_to_be(expectedWindowCount)
            )
        except TimeoutException:
            logger.warning(f"Timeout waiting for {expectedWindowCount} windows")
            return False

    def acceptCookies(self) -> "BasePage":
        logger.info("Attempting to accept cookies")
        try:
            if self.isElementVisible(self.COOKIE_ACCEPT, timeout=3):
                self.click(self.COOKIE_ACCEPT)
                logger.info("Cookies accepted via Accept All button")
                return self
        except (TimeoutException, ElementClickInterceptedException) as e:
            logger.debug(f"Accept All button not found or not clickable: {e}")

        logger.debug("No cookie banner found or already accepted")
        return self
