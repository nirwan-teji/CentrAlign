"""Human approval protocol used by the execution engine."""
from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable, Union

from core.state import HITLDecision, HITLRequest

DecisionHandler = Callable[[HITLRequest], Awaitable[Union[HITLRequest, HITLDecision, str]]]


class HITLManager:
    def __init__(self, handler: DecisionHandler | None = None) -> None:
        self.handler = handler

    async def request(self, request: HITLRequest) -> HITLRequest:
        if self.handler is None:
            return request
        response = await self.handler(request)
        if isinstance(response, HITLRequest):
            return response
        request.decision = HITLDecision(response)
        request.resolved_at = datetime.utcnow()
        return request
