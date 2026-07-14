"""
Axis ERP Integration Tool — payroll, tax compliance, employee management.

Connects to the Axis ERP API for Uganda payroll/tax operations.
Configure via AXIS_API_URL and AXIS_API_KEY environment variables.

Operations:
  - Payroll: process, status, history
  - Tax: PAYE calculation, URA returns, NSSF
  - Employees: list, details, contracts
"""

import os
import json
import logging
from enum import Enum
from typing import Optional
import httpx
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

AXIS_API_URL = os.environ.get("AXIS_API_URL", "")
AXIS_API_KEY = os.environ.get("AXIS_API_KEY", "")


class AxisPayrollOperation(str, Enum):
    PROCESS = "process_payroll"
    STATUS = "payroll_status"
    HISTORY = "payroll_history"
    PAYSLIP = "get_payslip"


class AxisTaxOperation(str, Enum):
    CALCULATE_PAYE = "calculate_paye"
    URA_RETURN = "ura_return"
    NSSF_CALC = "nssf_calculation"
    TAX_REPORT = "tax_report"


class AxisEmployeeOperation(str, Enum):
    LIST = "list_employees"
    DETAILS = "employee_details"
    CONTRACTS = "employee_contracts"
    LEAVE = "employee_leave"


async def _axis_api_call(endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
    """Make an API call to the Axis ERP backend."""
    if not AXIS_API_URL:
        return {"error": "AXIS_API_URL not configured. Set AXIS_API_URL and AXIS_API_KEY in environment."}
    
    url = f"{AXIS_API_URL.rstrip('/')}/api/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {AXIS_API_KEY}",
        "Content-Type": "application/json",
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=headers)
            elif method == "POST":
                resp = await client.post(url, headers=headers, json=data or {})
            else:
                return {"error": f"Unsupported method: {method}"}
            
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                return {"error": "Axis API authentication failed. Check AXIS_API_KEY."}
            elif resp.status_code == 404:
                return {"error": f"Axis endpoint not found: {endpoint}"}
            else:
                return {"error": f"Axis API returned {resp.status_code}: {resp.text[:200]}"}
    except httpx.RequestError as e:
        return {"error": f"Cannot reach Axis API at {AXIS_API_URL}: {e}"}
    except Exception as e:
        return {"error": f"Axis API call failed: {e}"}


class AxisPayrollTool(BaseTool):
    """Axis ERP payroll operations."""

    name = "axis_payroll"
    description = (
        "Axis ERP payroll operations. Process payroll, check status, "
        "view history, and get payslips. Operates in Uganda context (PAYE, NSSF)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Payroll operation to perform",
                "enum": [op.value for op in AxisPayrollOperation],
            },
            "period": {
                "type": "string",
                "description": "Payroll period (e.g., '2025-01', '2025-01-15'). Optional.",
            },
            "employee_id": {
                "type": "string",
                "description": "Employee ID for individual operations. Optional.",
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        period = kwargs.get("period")
        employee_id = kwargs.get("employee_id")

        if not AXIS_API_URL:
            return ToolResult(
                success=False,
                error="Axis ERP not configured. Set AXIS_API_URL and AXIS_API_KEY environment variables.",
            )

        try:
            if operation == AxisPayrollOperation.PROCESS.value:
                data = {"period": period} if period else {}
                result = await _axis_api_call("payroll/process", method="POST", data=data)
            elif operation == AxisPayrollOperation.STATUS.value:
                params = f"?period={period}" if period else ""
                result = await _axis_api_call(f"payroll/status{params}")
            elif operation == AxisPayrollOperation.HISTORY.value:
                params = f"?limit=10"
                if period:
                    params += f"&period={period}"
                result = await _axis_api_call(f"payroll/history{params}")
            elif operation == AxisPayrollOperation.PAYSLIP.value:
                if not employee_id:
                    return ToolResult(success=False, error="employee_id is required for get_payslip")
                params = f"?employee_id={employee_id}"
                if period:
                    params += f"&period={period}"
                result = await _axis_api_call(f"payroll/payslip{params}")
            else:
                return ToolResult(success=False, error=f"Unknown payroll operation: {operation}")

            if "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Axis payroll error: {e}")
            return ToolResult(success=False, error=str(e))


class AxisTaxTool(BaseTool):
    """Axis ERP tax compliance operations."""

    name = "axis_tax"
    description = (
        "Axis ERP tax compliance operations. Calculate PAYE, generate URA returns, "
        "compute NSSF, and generate tax reports. Uganda tax context."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Tax operation to perform",
                "enum": [op.value for op in AxisTaxOperation],
            },
            "period": {
                "type": "string",
                "description": "Tax period (e.g., '2025-01'). Optional.",
            },
            "gross_pay": {
                "type": "number",
                "description": "Gross pay amount for PAYE calculation. Optional.",
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        period = kwargs.get("period")
        gross_pay = kwargs.get("gross_pay")

        if not AXIS_API_URL:
            return ToolResult(
                success=False,
                error="Axis ERP not configured. Set AXIS_API_URL and AXIS_API_KEY environment variables.",
            )

        try:
            if operation == AxisTaxOperation.CALCULATE_PAYE.value:
                if not gross_pay:
                    return ToolResult(success=False, error="gross_pay is required for PAYE calculation")
                result = await _axis_api_call("tax/calculate-paye", method="POST", data={"gross_pay": gross_pay})
            elif operation == AxisTaxOperation.URA_RETURN.value:
                data = {"period": period} if period else {}
                result = await _axis_api_call("tax/ura-return", method="POST", data=data)
            elif operation == AxisTaxOperation.NSSF_CALC.value:
                data = {"gross_pay": gross_pay} if gross_pay else {}
                result = await _axis_api_call("tax/nssf", method="POST", data=data)
            elif operation == AxisTaxOperation.TAX_REPORT.value:
                params = f"?period={period}" if period else ""
                result = await _axis_api_call(f"tax/report{params}")
            else:
                return ToolResult(success=False, error=f"Unknown tax operation: {operation}")

            if "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Axis tax error: {e}")
            return ToolResult(success=False, error=str(e))


class AxisEmployeeTool(BaseTool):
    """Axis ERP employee management operations."""

    name = "axis_employees"
    description = (
        "Axis ERP employee management. List employees, get details, "
        "view contracts, and check leave balances."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": "Employee operation to perform",
                "enum": [op.value for op in AxisEmployeeOperation],
            },
            "employee_id": {
                "type": "string",
                "description": "Employee ID for individual operations. Optional.",
            },
        },
        "required": ["operation"],
    }

    async def run(self, **kwargs) -> ToolResult:
        operation = kwargs.get("operation", "")
        employee_id = kwargs.get("employee_id")

        if not AXIS_API_URL:
            return ToolResult(
                success=False,
                error="Axis ERP not configured. Set AXIS_API_URL and AXIS_API_KEY environment variables.",
            )

        try:
            if operation == AxisEmployeeOperation.LIST.value:
                result = await _axis_api_call("employees")
            elif operation == AxisEmployeeOperation.DETAILS.value:
                if not employee_id:
                    return ToolResult(success=False, error="employee_id is required for employee_details")
                result = await _axis_api_call(f"employees/{employee_id}")
            elif operation == AxisEmployeeOperation.CONTRACTS.value:
                params = f"?employee_id={employee_id}" if employee_id else ""
                result = await _axis_api_call(f"employees/contracts{params}")
            elif operation == AxisEmployeeOperation.LEAVE.value:
                if not employee_id:
                    return ToolResult(success=False, error="employee_id is required for employee_leave")
                result = await _axis_api_call(f"employees/{employee_id}/leave")
            else:
                return ToolResult(success=False, error=f"Unknown employee operation: {operation}")

            if "error" in result:
                return ToolResult(success=False, error=result["error"])

            return ToolResult(success=True, output=result)

        except Exception as e:
            logger.error(f"Axis employee error: {e}")
            return ToolResult(success=False, error=str(e))
