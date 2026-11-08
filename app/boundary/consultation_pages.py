"""Inbox and project consultation views for a full page or the message drawer."""
from flask import make_response, redirect, url_for

from app.boundary.ui import current_session_id, handle_expired, render, show_result
from app.common.request_types import ConsultationRequest
from app.common.result import Result
from app.control.consultation_controller import ConsultationController
from app.entity.database import INTERIOR_DESIGNER


class ConsultationPanel:
    # Uses one controller for the inbox, thread and project entry points.
    def __init__(self, role, endpoint):
        self.role = role
        self.endpoint = endpoint
        self.controller = ConsultationController()

    # Displays the inbox, a thread or the first-message form.
    def show(self, threadId, projectId, fragment):
        result = self.controller.execute(ConsultationRequest(current_session_id(), threadId, projectId), self.role)
        return handle_expired(result, self.role) or self._render(result, fragment)

    # Handles a message or close request, keeping the draft on validation errors.
    def submit(self, threadId, projectId, message, action, fragment):
        request = ConsultationRequest(current_session_id(), threadId, projectId, message)
        if action == "close":
            result = self.controller.close(request, self.role)
        elif action in ("", "send"):
            result = self.controller.send(request, self.role)
        else:
            result = Result.fail("INVALID_ACTION", "Choose a valid message action.")
        expired = handle_expired(result, self.role)
        if expired:
            return expired
        if result.ok:
            show_result(result)
            return redirect(url_for(self.endpoint, threadId=result.data["threadId"]), code=303)
        view = self.controller.execute(request, self.role)
        return handle_expired(view, self.role) or self._render(view, fragment, result.message, message[:2000])

    # Renders the same content for the regular page and the progressively enhanced drawer.
    def _render(self, result, fragment, error="", draft=""):
        template = "consultations/_panel.html" if fragment else "consultations/messages.html"
        response = make_response(render(template, result=result, error=error, draft=draft, fragment=fragment,
                                        endpoint=self.endpoint, is_designer=self.role == INTERIOR_DESIGNER))
        if fragment:
            response.headers["X-Consultation-Fragment"] = "1"
        return response
