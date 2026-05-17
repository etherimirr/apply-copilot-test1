"""Workday multi-step apply wizard.

Workday's flow:
  1. Sign in / create account (we expect the user to handle login manually)
  2. My Information (name, address, phone, work auth)
  3. My Experience (work history, education, resume upload)
  4. Application Questions
  5. Voluntary Disclosures
  6. Self-identification
  7. Review

Each step has a "Save and Continue" button. We run the generic filler on each
step, click Save+Continue, repeat. STOPS before the final Submit button.

Workday's DOM uses stable `data-automation-id` attributes across customers,
so we layer those on top of the generic label-based filler.
"""
from __future__ import annotations
from typing import Optional

from playwright.async_api import Page, TimeoutError as PWTimeoutError

from .filler import fill_application


# data-automation-id → canonical profile key
WORKDAY_FIELD_MAP = {
    "firstName": "first_name",
    "lastName": "last_name",
    "email": "email",
    "phone-number": "phone",
    "phoneNumber": "phone",
    "addressSection_addressLine1": "address1",
    "addressSection_city": "city",
    "addressSection_postalCode": "postal_code",
    "addressSection_countryRegion": "state",
}


NEXT_BUTTON_SELECTORS = [
    'button:has-text("Save and Continue")',
    'button:has-text("Continue")',
    'button[data-automation-id="bottom-navigation-next-button"]',
    'button[data-automation-id="pageFooterNextButton"]',
]

SUBMIT_BUTTON_SELECTORS = [
    'button:has-text("Submit")',
    'button[data-automation-id="bottom-navigation-submit-button"]',
    'button[data-automation-id="pageFooterSubmitButton"]',
]


async def _fill_workday_specific(page: Page, profile: dict) -> list[str]:
    """Try Workday's `data-automation-id` selectors for fields the generic
    label-based filler missed. Returns list of filled-field descriptions.
    """
    filled: list[str] = []
    for waid, profile_key in WORKDAY_FIELD_MAP.items():
        sel = f'input[data-automation-id="{waid}"]'
        try:
            loc = page.locator(sel).first
            if await loc.count() == 0:
                continue
            cur = await loc.input_value()
            if cur:
                continue
            val = profile.get(profile_key, "")
            if not val:
                continue
            await loc.fill(str(val), timeout=2000)
            filled.append(f"wd-{waid}={val[:30]!r}")
        except Exception:
            pass
    return filled


async def workday_run_to_submit(
    page: Page,
    profile: dict,
    *,
    jd: str = "",
    company: str = "",
    title: str = "",
    direction: str = "",
    resume_path: Optional["Path"] = None,
    max_steps: int = 8,
) -> dict:
    """Walk through Workday's multi-step wizard. Stops on the final Submit
    button — never clicks it. Returns aggregated step results.
    """
    step_reports: list[dict] = []
    for step in range(1, max_steps + 1):
        print(f"  [workday] step {step}")
        # Wait for the step to be ready
        try:
            await page.wait_for_selector("input, select, textarea, button", timeout=20000)
        except PWTimeoutError:
            return {"ok": False, "reason": f"step {step} never loaded",
                    "steps": step - 1, "results": step_reports}

        # Generic label-based fill
        report = await fill_application(
            page, profile, direction=direction, jd=jd,
            company=company, title=title, resume_path=resume_path, submit=False,
        )
        # Workday-specific data-automation-id pass for what generic missed
        wd_filled = await _fill_workday_specific(page, profile)
        report["filled"].extend(wd_filled)
        step_reports.append(report)

        # If final Submit visible → stop here, never click
        for s in SUBMIT_BUTTON_SELECTORS:
            try:
                if await page.locator(s).first.count() > 0:
                    return {"ok": True, "steps": step, "results": step_reports,
                            "stopped_at": "submit_button"}
            except Exception:
                pass

        # Click "Save and Continue" → next step
        clicked = False
        for sel in NEXT_BUTTON_SELECTORS:
            try:
                if await page.locator(sel).first.count() > 0:
                    await page.locator(sel).first.click(timeout=4000)
                    await page.wait_for_timeout(3000)
                    clicked = True
                    break
            except Exception:
                pass
        if not clicked:
            return {"ok": True, "steps": step, "results": step_reports,
                    "stopped_at": "no_next_button"}

    return {"ok": True, "steps": max_steps, "results": step_reports,
            "stopped_at": "max_steps_reached"}
