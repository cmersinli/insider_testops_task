import pytest
from pages import JobsPage


class TestInsider:

    def test_insider_qa_careers_flow(self, driver):
        try:
            jobsPage = JobsPage(driver)

            jobsPage.openQaJobsPage()
            assert jobsPage.isQaPageOpened(), "QA careers page did not open"

            openPositionsPage = jobsPage.clickSeeAllQaJobs()

            openPositionsPage.applyFilters("Istanbul, Turkiye", "Quality Assurance")

            assert openPositionsPage.isJobsListPresent(), "Jobs list not present"

            jobs = openPositionsPage.getAllJobs()

            if len(jobs) == 0:
                pytest.skip("No QA jobs currently available in Istanbul, Türkiye")

            for index, job in enumerate(jobs):
                try:
                    position = job["position"]
                    department = job["department"]
                    location = job["location"]

                    assert "Quality Assurance" in position, f"Job {index}: position mismatch - got '{position}'"
                    assert "Quality Assurance" in department, f"Job {index}: department mismatch - got '{department}'"
                    assert "Istanbul, Turkiye" in location, f"Job {index}: location mismatch - got '{location}'"
                except Exception as e:
                    raise AssertionError(f"Job {index} verification failed: {str(e)}") from e

            originalWindow = driver.current_window_handle

            for index in range(len(jobs)):
                try:
                    openPositionsPage.clickViewRole(jobIndex=index)
                    assert openPositionsPage.isLeverPageOpened(), f"Job {index}: Lever redirect failed"
                    driver.close()
                    driver.switch_to.window(originalWindow)
                    openPositionsPage.waitForPageReady()
                except Exception as e:
                    raise AssertionError(f"Job {index} View Role check failed: {str(e)}") from e

        except pytest.skip.Exception:
            raise
        except AssertionError:
            raise
        except Exception as e:
            raise AssertionError(f"Test failed unexpectedly: {str(e)}") from e
