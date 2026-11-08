"""US01-US12: registration, login, personal details, logout."""
from datetime import timedelta

import pytest

from app.common import clock
from app.common.request_types import RegistrationRequest, LoginRequest, SessionRequest, UpdateDetailsRequest
from app.control.account_controllers import (CreateCustomerAccountController, CreateDesignerAccountController,
                                             ViewPersonalDetailsController, UpdatePersonalDetailsController)
from app.control.login_controllers import (CustomerLoginController, DesignerLoginController, UserAdminLoginController,
                                           PlatformManagerLoginController, CustomerLogoutController,
                                           DesignerLogoutController, UserAdminLogoutController,
                                           PlatformManagerLogoutController, AccessGuardController)
from app.entity.sessions import Sessions
from app.entity.user_accounts import UserAccounts
from tests.conftest import PASSWORD, make_customer


# ---------------------------------------------------------------- US01 / US06 registration
@pytest.mark.parametrize("controller_class", [CreateCustomerAccountController, CreateDesignerAccountController])
class TestRegistration:
    # US01/US06: checks normal flow creates active account.
    def test_normal_flow_creates_active_account(self, controller_class):
        result = controller_class().execute(RegistrationRequest("Amy Tan", "amy@example.test", PASSWORD, "91234567"))
        assert result.ok and result.code == "CREATED"
        account = UserAccounts().findByEmail("amy@example.test")
        assert account.status == "ACTIVE"
        assert account.roleCode == controller_class.role

    # US01/US06: checks password is stored as salted hash.
    def test_password_is_stored_as_salted_hash(self, controller_class):
        controller_class().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        account = UserAccounts().findByEmail("amy@example.test")
        assert PASSWORD not in account.passwordHash and account.checkPassword(PASSWORD)

    # US01/US06: checks invalid details are rejected and nothing is saved.
    @pytest.mark.parametrize("name,email,password,contact", [
        ("", "amy@example.test", PASSWORD, "91234567"),
        ("Amy", "not-an-email", PASSWORD, "91234567"),
        ("Amy", "amy@example.test", "short", "91234567"),
        ("Amy", "amy@example.test", PASSWORD, "12ab"),
        ("Amy", "amy@example.test", PASSWORD, ""),
    ])
    def test_invalid_details_save_nothing(self, controller_class, name, email, password, contact):
        result = controller_class().execute(RegistrationRequest(name, email, password, contact))
        assert not result.ok and result.code == "INVALID_INPUT"
        assert not UserAccounts().isEmailRegistered("amy@example.test")

    # US01/US06: checks email already registered.
    def test_email_already_registered(self, controller_class):
        controller_class().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        result = controller_class().execute(RegistrationRequest("Amy 2", "AMY@example.test", PASSWORD, "91234567"))
        assert result.code == "EMAIL_TAKEN" and result.message == "This email is already registered"


# ---------------------------------------------------------------- US02 / US07 / US09 / US11 login
class TestLogin:
    # US02/US07/US09/US11: checks customer normal flow creates session.
    def test_customer_normal_flow_creates_session(self):
        CreateCustomerAccountController().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        result = CustomerLoginController().execute(LoginRequest("amy@example.test", PASSWORD))
        assert result.ok and Sessions().isActive(result.data["sessionId"])

    # US02/US07/US09/US11: checks blank email and password are rejected.
    def test_empty_fields(self):
        result = CustomerLoginController().execute(LoginRequest("", ""))
        assert result.code == "INVALID_INPUT"

    # US02/US07/US09/US11: checks unknown email and wrong password give same message.
    def test_unknown_email_and_wrong_password_give_same_message(self):
        CreateCustomerAccountController().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        unknown = CustomerLoginController().execute(LoginRequest("nobody@example.test", PASSWORD))
        wrong = CustomerLoginController().execute(LoginRequest("amy@example.test", "WrongPass1"))
        assert unknown.message == wrong.message == "Invalid email or password"

    # US02/US07/US09/US11: checks the wrong login page is refused.
    def test_wrong_role(self):
        CreateCustomerAccountController().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        result = DesignerLoginController().execute(LoginRequest("amy@example.test", PASSWORD))
        assert result.code == "WRONG_ROLE"

    # US02/US07/US09/US11: checks a suspended account cannot log in.
    def test_suspended_account(self, fresh_db):
        CreateCustomerAccountController().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        fresh_db.execute("UPDATE user_accounts SET status = 'SUSPENDED'")
        result = CustomerLoginController().execute(LoginRequest("amy@example.test", PASSWORD))
        assert result.code == "SUSPENDED"

    # US02/US07/US09/US11: checks a suspended profile blocks its accounts' login.
    def test_suspended_profile(self, fresh_db):
        CreateCustomerAccountController().execute(RegistrationRequest("Amy", "amy@example.test", PASSWORD, "91234567"))
        fresh_db.execute("UPDATE user_profiles SET status = 'SUSPENDED' WHERE role_code = 'CUSTOMER'")
        result = CustomerLoginController().execute(LoginRequest("amy@example.test", PASSWORD))
        assert result.code == "SUSPENDED"

    # US02/US07/US09/US11: checks staff accounts log in on their own pages.
    @pytest.mark.parametrize("controller_class,role", [(UserAdminLoginController, "USER_ADMIN"),
                                                       (PlatformManagerLoginController, "PLATFORM_MANAGER")])
    def test_staff_login(self, fresh_db, controller_class, role):
        from werkzeug.security import generate_password_hash
        fresh_db.execute("INSERT INTO user_accounts (name, email, password_hash, profile_id, created_at, updated_at) "
                         "SELECT 'Staff', 'staff@example.test', ?, profile_id, '2026-01-01 00:00:00', "
                         "'2026-01-01 00:00:00' FROM user_profiles WHERE role_code = ?",
                         (generate_password_hash(PASSWORD), role))
        assert controller_class().execute(LoginRequest("staff@example.test", PASSWORD)).ok
        assert CustomerLoginController().execute(LoginRequest("staff@example.test", PASSWORD)).code == "WRONG_ROLE"


# ---------------------------------------------------------------- US03 / US04 personal details
class TestPersonalDetails:
    # US03/US04: checks view own details.
    def test_view_own_details(self):
        session_id = make_customer()
        result = ViewPersonalDetailsController().execute(SessionRequest(session_id))
        assert result.ok and result.data["email"] == "amy@example.test"
        assert "passwordHash" not in result.data

    # US03/US04: checks view session expired.
    def test_view_session_expired(self, frozen_clock):
        session_id = make_customer()
        clock.freeze(frozen_clock + timedelta(minutes=31))
        assert ViewPersonalDetailsController().execute(SessionRequest(session_id)).code == "SESSION_EXPIRED"

    # US03/US04: checks update normal flow.
    def test_update_normal_flow(self):
        session_id = make_customer()
        result = UpdatePersonalDetailsController().execute(UpdateDetailsRequest(session_id, "Amy Lim", "+6588887777"))
        assert result.ok and result.message == "Your details have been updated."
        details = ViewPersonalDetailsController().execute(SessionRequest(session_id)).data
        assert details["name"] == "Amy Lim" and details["contactNumber"] == "+6588887777"

    # US03/US04: checks update invalid details.
    @pytest.mark.parametrize("name,contact", [("", "91234567"), ("Amy", "abc")])
    def test_update_invalid_details(self, name, contact):
        session_id = make_customer()
        result = UpdatePersonalDetailsController().execute(UpdateDetailsRequest(session_id, name, contact))
        assert result.code == "INVALID_INPUT"
        assert ViewPersonalDetailsController().execute(SessionRequest(session_id)).data["name"] == "Amy Tan"

    # US03/US04: checks update session expired.
    def test_update_session_expired(self):
        result = UpdatePersonalDetailsController().execute(UpdateDetailsRequest("bogus", "Amy", "91234567"))
        assert result.code == "SESSION_EXPIRED"


# ---------------------------------------------------------------- US05 / US08 / US10 / US12 logout
@pytest.mark.parametrize("controller_class", [CustomerLogoutController, DesignerLogoutController,
                                              UserAdminLogoutController, PlatformManagerLogoutController])
class TestLogout:
    # US05/US08/US10/US12: checks normal flow deletes session.
    def test_normal_flow_deletes_session(self, controller_class):
        session_id = make_customer()
        result = controller_class().execute(SessionRequest(session_id))
        assert result.ok and result.message == "You have been logged out."
        assert not Sessions().isActive(session_id)

    # US05/US08/US10/US12: checks session already expired still succeeds.
    def test_session_already_expired_still_succeeds(self, controller_class):
        assert controller_class().execute(SessionRequest("expired-or-unknown")).ok


# ---------------------------------------------------------------- shared access guard
# Checks the shared access guard refuses other roles and ended sessions.
def test_access_guard_blocks_other_roles_and_expired_sessions(frozen_clock):
    session_id = make_customer()
    assert AccessGuardController().execute(SessionRequest(session_id), "CUSTOMER").ok
    assert AccessGuardController().execute(SessionRequest(session_id), "USER_ADMIN").code == "FORBIDDEN"
    clock.freeze(frozen_clock + timedelta(minutes=31))
    assert AccessGuardController().execute(SessionRequest(session_id), "CUSTOMER").code == "SESSION_EXPIRED"
