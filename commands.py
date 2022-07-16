from abc import ABCMeta

import sublime
from LSP.plugin import Request
from LSP.plugin.core.registry import LspTextCommand
from LSP.plugin.core.typing import Union
from .utils import get_setting

from .constants import (
    PACKAGE_NAME,
    REQ_CHECK_STATUS,
    REQ_NOTIFY_ACCEPTED,
    REQ_NOTIFY_REJECTED,
    REQ_SIGN_IN_CONFIRM,
    REQ_SIGN_IN_INITIATE,
    REQ_SIGN_OUT,
)
from .plugin import CopilotPlugin
from .types import (
    CopilotPayloadNotifyAccepted,
    CopilotPayloadNotifyRejected,
    CopilotPayloadSignInConfirm,
    CopilotPayloadSignInInitiate,
    CopilotPayloadSignOut,
)
from .ui import Completion


class CopilotTextCommand(LspTextCommand, metaclass=ABCMeta):
    session_name = PACKAGE_NAME

    def want_event(self) -> bool:
        return False

    def _record_telemetry(
        self,
        request: str,
        payload: Union[CopilotPayloadNotifyAccepted, CopilotPayloadNotifyRejected],
    ) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return

        if not get_setting(session, "telemetry", False):
            return

        session.send_request(
            Request(request, payload),
            lambda _: None,
        )


class CopilotAcceptSuggestionCommand(CopilotTextCommand):
    def run(self, edit: sublime.Edit) -> None:
        completion = Completion(self.view)

        if not completion.is_visible():
            return

        region = completion.region
        if not region:
            return

        self.view.insert(edit, region[1], completion.display_text)

        # TODO: When a suggestion is accept, we need to send a REQ_NOTIFY_REJECTED
        # request with all other completions which weren't accepted
        self._record_telemetry(REQ_NOTIFY_ACCEPTED, {"uuid": completion.uuid})

        completion.hide()


class CopilotRejectSuggestionCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        completion = Completion(self.view)

        # TODO: Currently we send the last shown completion UUID, however Copilot can
        # suggest multiple UUID's. We need to return all UUID's which were not accepted
        self._record_telemetry(REQ_NOTIFY_REJECTED, {"uuids": [completion.uuid]})

        completion.hide()


class CopilotCheckStatusCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(Request(REQ_CHECK_STATUS), self._on_result_check_status)

    def _on_result_check_status(self, payload: Union[CopilotPayloadSignInConfirm, CopilotPayloadSignOut]) -> None:
        if payload.get("status") == "OK":
            CopilotPlugin.set_has_signed_in(True)
            sublime.message_dialog('[LSP-Copilot] Sign in OK with user "{}".'.format(payload.get("user")))
        else:
            CopilotPlugin.set_has_signed_in(False)
            sublime.message_dialog("[LSP-Copilot] You haven't signed in yet.")


class CopilotSignInCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(Request(REQ_SIGN_IN_INITIATE), self._on_result_sign_in_initiate)

    def _on_result_sign_in_initiate(
        self,
        payload: Union[CopilotPayloadSignInConfirm, CopilotPayloadSignInInitiate],
    ) -> None:
        CopilotPlugin.set_has_signed_in(False)
        if payload.get("status") == "AlreadySignedIn":
            CopilotPlugin.set_has_signed_in(True)
            return
        user_code = payload.get("userCode")
        verification_uri = payload.get("verificationUri")
        if not (user_code and verification_uri):
            return
        sublime.set_clipboard(user_code)
        sublime.run_command("open_url", {"url": verification_uri})
        if not sublime.ok_cancel_dialog(
            "[LSP-Copilot] The device activation code has been copied."
            + " Please paste it in the popup GitHub page. Press OK when completed."
        ):
            return
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(
            Request(REQ_SIGN_IN_CONFIRM, {"userCode": user_code}),
            self._on_result_sign_in_confirm,
        )

    def _on_result_sign_in_confirm(self, payload: CopilotPayloadSignInConfirm) -> None:
        if payload.get("status") == "OK":
            CopilotPlugin.set_has_signed_in(True)
            sublime.message_dialog('[LSP-Copilot] Sign in OK with user "{}".'.format(payload.get("user")))

    def is_enabled(self) -> bool:
        session = self.session_by_name(self.session_name)
        if not session:
            return not CopilotPlugin.get_has_signed_in()
        return not CopilotPlugin.get_has_signed_in() or get_setting(session, "debug", False)


class CopilotSignOutCommand(CopilotTextCommand):
    def run(self, _: sublime.Edit) -> None:
        session = self.session_by_name(self.session_name)
        if not session:
            return
        session.send_request(Request(REQ_SIGN_OUT), self._on_result_sign_out)

    def _on_result_sign_out(self, payload: CopilotPayloadSignOut) -> None:
        if payload.get("status") == "NotSignedIn":
            CopilotPlugin.set_has_signed_in(False)
            sublime.message_dialog("[LSP-Copilot] Sign out OK. Bye!")
