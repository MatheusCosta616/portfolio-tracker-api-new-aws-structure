"""Non-destructive smoke checks for a deployed Portfolio Tracker API."""

from __future__ import annotations

import os
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    duration_ms: int


BASE_URL = os.getenv("QA_BASE_URL", "http://52.3.97.206:8000").rstrip("/")
TIMEOUT = float(os.getenv("QA_TIMEOUT", "10"))
RETRIES = int(os.getenv("QA_RETRIES", "2"))
REPORT_PATH = Path(os.getenv("QA_REPORT", "qa-results/remote-smoke.xml"))


class SmokeRunner:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.results: list[CheckResult] = []

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        url = f"{BASE_URL}{path}"
        last_error: Exception | None = None
        for attempt in range(RETRIES + 1):
            try:
                response = self.session.request(method, url, timeout=TIMEOUT, **kwargs)
                if response.status_code >= 500 and attempt < RETRIES:
                    time.sleep(2**attempt)
                    continue
                return response
            except requests.RequestException as error:
                last_error = error
                if attempt < RETRIES:
                    time.sleep(2**attempt)
        raise RuntimeError(f"request failed: {url}: {last_error}")

    def check(self, name: str, callback: Any) -> None:
        started = time.perf_counter()
        try:
            detail = callback()
            duration_ms = round((time.perf_counter() - started) * 1000)
            self.results.append(CheckResult(name, "passed", str(detail), duration_ms))
            print(f"PASS {name}: {detail} ({duration_ms} ms)")
        except Exception as error:  # noqa: BLE001 - a check must be reported, not abort the suite
            duration_ms = round((time.perf_counter() - started) * 1000)
            self.results.append(CheckResult(name, "failed", str(error), duration_ms))
            print(f"FAIL {name}: {error} ({duration_ms} ms)")

    @staticmethod
    def expect_status(response: requests.Response, *statuses: int) -> dict[str, Any]:
        if response.status_code not in statuses:
            body = response.text[:500].replace("\n", " ")
            raise AssertionError(f"expected {statuses}, got {response.status_code}: {body}")
        try:
            return response.json()
        except ValueError as error:
            raise AssertionError("response is not valid JSON") from error

    def run(self) -> int:
        self.check("api-health", self.api_health)
        self.check("openapi-schema", self.openapi_schema)
        self.check("swagger-page", self.swagger_page)
        self.check("unauthenticated-profile", self.unauthenticated_profile)
        self.check("unauthenticated-portfolios", self.unauthenticated_portfolios)
        self.check("invalid-login", self.invalid_login)

        if os.getenv("QA_RUN_MUTATING", "false").lower() == "true":
            self.check("register-same-name-different-emails", self.register_same_name)

        self.write_report()
        failed = sum(result.status == "failed" for result in self.results)
        return 1 if failed else 0

    def api_health(self) -> str:
        response = self.request("GET", "/api/schema/", headers={"Accept": "application/json"})
        self.expect_status(response, 200)
        return "schema endpoint available"

    def openapi_schema(self) -> str:
        response = self.request("GET", "/api/schema/", headers={"Accept": "application/json"})
        schema = self.expect_status(response, 200)
        if not isinstance(schema, dict) or "paths" not in schema:
            raise AssertionError("OpenAPI document does not contain paths")
        required_paths = {"/api/auth/login", "/api/auth/register", "/api/portfolios/"}
        missing = sorted(required_paths - set(schema["paths"]))
        if missing:
            raise AssertionError(f"missing OpenAPI paths: {missing}")
        return f"{len(schema['paths'])} paths published"

    def swagger_page(self) -> str:
        response = self.request("GET", "/api/docs/")
        if response.status_code != 200 or "swagger" not in response.text.lower():
            raise AssertionError(f"expected Swagger HTML, got {response.status_code}")
        return "Swagger UI available"

    def unauthenticated_profile(self) -> str:
        response = self.request("GET", "/api/auth/me")
        self.expect_status(response, 401)
        return "protected endpoint rejected anonymous request"

    def unauthenticated_portfolios(self) -> str:
        response = self.request("GET", "/api/portfolios/")
        self.expect_status(response, 401)
        return "protected endpoint rejected anonymous request"

    def invalid_login(self) -> str:
        response = self.request(
            "POST",
            "/api/auth/login",
            json={"email": "qa-invalid@example.com", "password": "invalid-password"},
        )
        self.expect_status(response, 401)
        return "invalid credentials rejected"

    def register_same_name(self) -> str:
        suffix = uuid.uuid4().hex
        payload = {"username": "qa-same-name", "password": "QaStrongPass123!"}
        statuses = []
        for label in ("a", "b"):
            payload["email"] = f"qa-{suffix}-{label}@example.com"
            response = self.request("POST", "/api/auth/register", json=payload)
            self.expect_status(response, 201)
            statuses.append(response.status_code)
        return f"two registrations accepted: {statuses}"

    def write_report(self) -> None:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        suite = ET.Element("testsuite", name="remote-smoke", tests=str(len(self.results)))
        failures = 0
        total_time = 0.0
        for result in self.results:
            total_time += result.duration_ms / 1000
            case = ET.SubElement(
                suite,
                "testcase",
                name=result.name,
                time=f"{result.duration_ms / 1000:.3f}",
            )
            if result.status == "failed":
                failures += 1
                ET.SubElement(case, "failure", message=result.detail).text = result.detail
            else:
                ET.SubElement(case, "system-out").text = result.detail
        suite.set("failures", str(failures))
        suite.set("time", f"{total_time:.3f}")
        ET.ElementTree(suite).write(REPORT_PATH, encoding="utf-8", xml_declaration=True)
        print(f"JUnit report: {REPORT_PATH}")


if __name__ == "__main__":
    sys.exit(SmokeRunner().run())
