import logging
import os
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from .base_page import BasePage, retryOnStaleElement

logger = logging.getLogger(__name__)


class OpenPositionsPage(BasePage):

    LOCATION_DROPDOWN = (By.ID, "filter-by-location")
    DEPARTMENT_DROPDOWN = (By.ID, "filter-by-department")
    JOBS_LIST = (By.ID, "jobs-list")
    JOB_ITEM = (By.CSS_SELECTOR, "div.position-list-item-wrapper")
    JOB_POSITION = (By.CSS_SELECTOR, "p.position-title")
    JOB_DEPARTMENT = (By.CSS_SELECTOR, "span.position-department")
    JOB_LOCATION = (By.CSS_SELECTOR, "div.position-location")
    VIEW_ROLE_BTN = (By.XPATH, "//a[text()='View Role']")
    NO_JOBS_MSG = (By.CSS_SELECTOR, ".no-job-result")

    FILTER_SELECT_WAIT = int(os.getenv("FILTER_SELECT_WAIT", 3))
    FILTER_APPLY_WAIT = int(os.getenv("FILTER_APPLY_WAIT", 5))

    def initializePage(self) -> "OpenPositionsPage":
        logger.info("Initializing Open Positions page")
        self.waitForPageReady()
        self.acceptCookies()
        self.waitForFiltersToLoad()
        logger.info("Waiting for jobs to load with default 'All' filter")
        self.waitForJobsToAppear()
        return self

    def waitForPageReady(self) -> None:
        try:
            WebDriverWait(self.driver, self.DEFAULT_TIMEOUT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            logger.warning("Page ready state timeout")

    def waitForFiltersToLoad(self) -> None:
        logger.info("Waiting for filter dropdowns to load")
        try:
            self.waitForElementVisible(self.LOCATION_DROPDOWN, timeout=20)
            self.waitForElementVisible(self.DEPARTMENT_DROPDOWN, timeout=20)

            locationOptionSelector = (By.CSS_SELECTOR, "#filter-by-location option[class*='job-location']")
            departmentOptionSelector = (By.CSS_SELECTOR, "#filter-by-department option[class*='job-team']")

            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(locationOptionSelector)
            )
            logger.info("Location dropdown options with job-location class loaded")

            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located(departmentOptionSelector)
            )
            logger.info("Department dropdown options with job-team class loaded")

        except TimeoutException:
            logger.warning("Timeout waiting for filters to load")

    @retryOnStaleElement(maxAttempts=3)
    def selectLocationFilter(self, location: str) -> "OpenPositionsPage":
        logger.info(f"Selecting location filter: {location}")
        self.waitForFiltersToLoad()

        try:
            locationElement = self.waitForElementClickable(self.LOCATION_DROPDOWN)
            locationSelect = Select(locationElement)

            for option in locationSelect.options:
                if location.lower() in option.text.lower():
                    locationSelect.select_by_visible_text(option.text)
                    logger.info(f"Selected location: {option.text}")
                    time.sleep(self.FILTER_SELECT_WAIT)
                    return self

            availableOptions = [opt.text for opt in locationSelect.options]
            logger.error(f"Location '{location}' not found. Available: {availableOptions}")
            raise Exception(f"Location '{location}' not in dropdown options")

        except TimeoutException:
            logger.error("Location dropdown not found or not clickable")
            raise Exception("Location dropdown not found")

    @retryOnStaleElement(maxAttempts=3)
    def selectDepartmentFilter(self, department: str) -> "OpenPositionsPage":
        logger.info(f"Selecting department filter: {department}")
        try:
            deptElement = self.waitForElementClickable(self.DEPARTMENT_DROPDOWN)
            deptSelect = Select(deptElement)

            for option in deptSelect.options:
                if department.lower() in option.text.lower():
                    deptSelect.select_by_visible_text(option.text)
                    logger.info(f"Selected department: {option.text}")
                    time.sleep(self.FILTER_SELECT_WAIT)
                    return self

            availableOptions = [opt.text for opt in deptSelect.options]
            logger.error(f"Department '{department}' not found. Available: {availableOptions}")
            raise Exception(f"Department '{department}' not in dropdown options")

        except TimeoutException:
            logger.error("Department dropdown not found or not clickable")
            raise Exception("Department dropdown not found")

    def waitForJobsToAppear(self, timeout: int = 30) -> bool:
        logger.info("Waiting for jobs to appear")
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(self.JOB_ITEM)
            )
            return True
        except TimeoutException:
            logger.warning("No jobs appeared within timeout")
            return False

    def applyFilters(self, location: str, department: str) -> "OpenPositionsPage":
        logger.info(f"Applying filters - Location: {location}, Department: {department}")
        self.selectLocationFilter(location)
        self.selectDepartmentFilter(department)
        time.sleep(self.FILTER_APPLY_WAIT)
        self.waitForJobsToAppear(timeout=15)
        return self

    def isJobsListPresent(self) -> bool:
        logger.info("Checking if jobs list is present")
        try:
            noJobsElements = self.driver.find_elements(*self.NO_JOBS_MSG)
            if noJobsElements and noJobsElements[0].is_displayed():
                logger.info("No jobs message displayed")
                return False
            jobsList = self.waitForElementVisible(self.JOBS_LIST, timeout=10)
            jobItems = jobsList.find_elements(*self.JOB_ITEM)
            jobCount = len(jobItems)
            logger.info(f"Found {jobCount} job items")
            return jobCount > 0
        except TimeoutException:
            logger.warning("Jobs list not found within timeout")
            return False

    def getAllJobs(self) -> list[dict]:
        logger.info("Retrieving all job listings")
        jobs = []
        jobItems = self.findElements(self.JOB_ITEM, timeout=10)

        for item in jobItems:
            jobData = {"position": "", "department": "", "location": ""}
            try:
                positionElem = item.find_element(*self.JOB_POSITION)
                jobData["position"] = positionElem.text.strip()
            except NoSuchElementException:
                pass

            try:
                deptElem = item.find_element(*self.JOB_DEPARTMENT)
                jobData["department"] = deptElem.text.strip()
            except NoSuchElementException:
                pass

            try:
                locElem = item.find_element(*self.JOB_LOCATION)
                jobData["location"] = locElem.text.strip()
            except NoSuchElementException:
                pass

            if jobData["position"]:
                jobs.append(jobData)

        logger.info(f"Retrieved {len(jobs)} jobs")
        return jobs

    def clickViewRole(self, jobIndex: int = 0) -> None:
        logger.info(f"Clicking 'View Role' for job at index {jobIndex}")
        jobItems = self.findElements(self.JOB_ITEM, timeout=10)

        if not jobItems or len(jobItems) <= jobIndex:
            logger.error(f"No job found at index {jobIndex}")
            raise Exception(f"No job found at index {jobIndex}")

        targetJob = jobItems[jobIndex]
        self.scrollToWebElement(targetJob)
        ActionChains(self.driver).move_to_element(targetJob).perform()

        try:
            viewRoleBtn = WebDriverWait(targetJob, 5).until(
                lambda el: el.find_element(*self.VIEW_ROLE_BTN)
            )
        except TimeoutException:
            logger.debug("Primary View Role button not found, trying lever link")
            try:
                viewRoleBtn = targetJob.find_element(By.CSS_SELECTOR, "a[href*='lever']")
            except NoSuchElementException:
                logger.error("No View Role button found")
                raise Exception("View Role button not found")

        self.driver.execute_script("arguments[0].click();", viewRoleBtn)
        logger.info("Clicked View Role button")

    def isLeverPageOpened(self) -> bool:
        logger.info("Checking if Lever page is opened")
        self.waitForNewWindow(expectedWindowCount=2, timeout=10)

        windowHandles = self.driver.window_handles
        if len(windowHandles) > 1:
            self.driver.switch_to.window(windowHandles[-1])
            logger.info(f"Switched to new tab, total tabs: {len(windowHandles)}")

        try:
            self.waitForUrlContains("lever", timeout=15)
        except TimeoutException:
            logger.warning("Lever URL not detected in URL")

        currentUrl = self.getCurrentUrl().lower()
        isLever = "lever.co" in currentUrl or "jobs.lever" in currentUrl
        logger.info(f"Current URL: {currentUrl}, Is Lever: {isLever}")
        return isLever
