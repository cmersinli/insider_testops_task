import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from .base_page import BasePage
from .open_positions_page import OpenPositionsPage

logger = logging.getLogger(__name__)


class JobsPage(BasePage):

    URL = "https://useinsider.com/careers/quality-assurance/"

    SEE_ALL_QA_JOBS = (By.XPATH, "//a[contains(text(), 'See all QA jobs')]")

    def openQaJobsPage(self) -> "JobsPage":
        logger.info("Opening QA Jobs page")
        self.open(self.URL)
        self.waitForPageReady()
        self.acceptCookies()
        return self

    def waitForPageReady(self) -> None:
        try:
            WebDriverWait(self.driver, self.DEFAULT_TIMEOUT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning("Page ready state timeout")

    def isQaPageOpened(self) -> bool:
        currentUrl = self.getCurrentUrl().lower()
        urlValid = "insider" in currentUrl and "careers" in currentUrl
        pageTitle = self.driver.title.lower()
        titleValid = "insider" in pageTitle
        logger.info(f"QA page validation - URL valid: {urlValid}, Title valid: {titleValid}")
        return urlValid or titleValid

    def clickSeeAllQaJobs(self) -> "OpenPositionsPage":
        logger.info("Clicking 'See all QA jobs' button")
        try:
            seeAllBtn = self.waitForElementVisible(self.SEE_ALL_QA_JOBS)
            self.scrollToWebElement(seeAllBtn)
            self.driver.execute_script("arguments[0].click();", seeAllBtn)
            logger.info("Clicked 'See all QA jobs' button")
        except TimeoutException:
            logger.error("See all QA jobs button not found")
            raise Exception("See all QA jobs button not found")

        openPositionsPage = OpenPositionsPage(self.driver)
        openPositionsPage.initializePage()
        return openPositionsPage
