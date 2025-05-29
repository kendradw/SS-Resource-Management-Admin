#region ---- Usage Sample ----
""" if __name__ == "__main__":
     SHEETS = ["https://app.smartsheet.com/sheets/695wjPhPvCxh5m9Jpjf9FF3Fv97c2mF5cc75Rmw1?view=grid"]
     bot = SmartsheetBot(email=ss_username, password=ss_password, headless=False) #false for visibilty
     bot.login()
     for sheet_url in SHEETS:
         bot.track_workload(sheet_url)
     bot.close()"""
#endregion
#region ---- Imports ----
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.common.exceptions import StaleElementReferenceException
import time
import logging
from configs.setup_logger import setup_logger
import configs.crypter as crypter
import sys
import os
#endregion

class SmartsheetBot:
    def __init__(self, email, password, logger: logging.Logger, headless=True):
        self.log = logger
        
        self.email = email
        self.password = password

        options = Options()
        if headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 100)

    #region ---- Log-in to Smartsheet ----
    def auto_login(self):
        """Auto login to smartsheet with automation@dowbuilt.com account"""

        self.driver.get("https://app.smartsheet.com/b/home")

        # Email input
        email_input = self.wait.until(EC.presence_of_element_located((By.ID, "loginEmail")))
        email_input.send_keys(self.email)

        # Continue
        continue_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "formControl")))
        continue_btn.click()

        # Sign in with email/password
        sign_in_btn = self.wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "emailPasswordOption")))
        sign_in_btn.click()

        # Password input
        password_input = self.wait.until(EC.presence_of_element_located((By.ID, "loginPassword")))
        password_input.send_keys(self.password)

        # Final sign-in
        submit_btn = self.wait.until(EC.element_to_be_clickable((By.ID, "formControl")))
        submit_btn.click()

        self.log.info("Logged in...")
        return
      
    def user_login_manual(self):
        """Waits for the user to manually enter their username, password, and authenticate through MFA. 
        Will wait 200 seconds. """
        self.driver.get("https://app.smartsheet.com/b/home")
        self.log.info("Please log in manually...")

        # Wait until a specific element that only appears after login is present
        wait = WebDriverWait(self.driver, 200)
        try:
            wait.until(EC.url_contains("=home"))  
            self.log.info("Login detected. Continuing...")
        except TimeoutException:
            self.log.error("Login timeout. Please check if login was successful or increase wait time.")
            raise
        return

    def user_login_auto(self):
        """Will input user log-in data for microsoft log-in requires user to complete MFA Verification."""
        username = crypter.decrypt_from_config("user")
        password = crypter.decrypt_from_config("pass")
 
        self.driver.get("https://app.smartsheet.com/b/home")

        #Click "Sign in with Microsoft"
        self.wait.until(EC.element_to_be_clickable((By.ID, "azureButton"))).click()

        #Enter email
        self.wait.until(EC.presence_of_element_located((By.ID, "i0116"))).send_keys(username)
        for _ in range(3):
            try:
                self.wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
                break
            except StaleElementReferenceException:
                time.sleep(1)

        #Enter password
        self.wait.until(EC.presence_of_element_located((By.ID, "i0118"))).send_keys(password)
        for _ in range(3):
            try:
                self.wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
                break
            except StaleElementReferenceException:
                time.sleep(1)

        # Stay signed in:
        for _ in range(3):
            try:
                self.wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9"))).click()
                break
            except StaleElementReferenceException:
                time.sleep(1)

        # Step 4: Wait for login
        self.wait.until(EC.url_contains("/home"))  
        self.log.info("Login detected. Continuing...")
    #endregion
    #region ---- Workload Tracking  ----
    def track_workload(self, sheet_url):
        self.driver.get(sheet_url)
        time.sleep(2)
        self.wait_short = WebDriverWait(self.driver, 10)
        try:
            try:
                workload_btn = self.wait_short.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-client-id="tk-landing-panel-track-workload-btn"]'))
                )
                self.log.info("RM tab already open.")
            except TimeoutException:
                # RM tab not open yet, click the tab
                resource_tab = self.wait.until(
                    EC.element_to_be_clickable((By.ID, "rtr-16"))
                )
                resource_tab.click()
                self.log.info("Opened RM tab.")
                time.sleep(7)  # give it time to load

            # Click "Track workload" button
            try:
                workload_btn = self.wait.until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-client-id="tk-landing-panel-track-workload-btn"]'))
                )
                workload_btn.click()
                self.log.info(f"Tracked workload for: {sheet_url}")
            except Exception as e:
                self.log.info(f"Track Workload button not found. RM Projects possibly already created for {sheet_url}")

            #Click "Connect Project" button
            connect_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[data-client-id="tk-c-7"]'))
            )
            connect_btn.click()
            self.log.info(f"Connected project for: {sheet_url}")
            return True

        except Exception as e:
            self.log.info(f"Failed to track workload for {sheet_url}: {e}")
            return False
    #endregion
    #region ---- Destruct / Close ----
    def close(self):
        """Close the browser session."""
        if self.driver: 
            self.driver.quit()
            self.log.info("Browser session closed.")
        else:
            self.log.info("No browser session to close.")
    #destructor
    def __del__(self):
        self.close()
    #endregion



