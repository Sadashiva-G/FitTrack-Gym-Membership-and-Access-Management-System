"""FitTrack: Gym Membership and Access Management System - Streamlit Frontend.

Built with 100% pure Python and Streamlit. Communicates with the FastAPI backend via requests.
"""

from datetime import date, datetime
import os
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.getenv("FITTRACK_API_URL", "https://fittrack-gym-membership-and-access.onrender.com/docs")


# ---------------------------------------------------------------------------
# API Communication Helper
# ---------------------------------------------------------------------------

def api_call(
    method: str,
    endpoint: str,
    json_data: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Any], Optional[str]]:
    """Execute an HTTP request to the FastAPI backend.

    Catches connection errors and formats error details without exposing tracebacks.
    Returns (data, error_message).
    """
    url = f"{BACKEND_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = requests.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
            timeout=10,
        )
        if 200 <= resp.status_code < 300:
            return resp.json(), None
        try:
            err_data = resp.json()
            detail = err_data.get("detail", f"Error {resp.status_code}: {resp.text}")
        except Exception:
            detail = f"Error {resp.status_code}: {resp.text}"
        return None, detail
    except requests.exceptions.ConnectionError:
        return None, (
            f"Cannot connect to FitTrack backend at {BACKEND_URL}. "
            "Please ensure the FastAPI backend is running (uvicorn backend.main:app)."
        )
    except requests.exceptions.Timeout:
        return None, "Backend request timed out. Please try again."
    except Exception as exc:
        return None, f"Request failed: {str(exc)}"


def check_backend_health() -> bool:
    """Check if the backend API is online."""
    data, err = api_call("GET", "/health")
    return err is None and isinstance(data, dict) and data.get("status") == "ok"


# ---------------------------------------------------------------------------
# Page Setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FitTrack - Gym Management",
    page_icon="🏋️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize Session State
if "last_action_message" not in st.session_state:
    st.session_state.last_action_message = None
if "last_action_type" not in st.session_state:
    st.session_state.last_action_type = "success"
if "checkin_result" not in st.session_state:
    st.session_state.checkin_result = None


def set_flash_message(msg: str, msg_type: str = "success") -> None:
    """Store a flash message to display after st.rerun."""
    st.session_state.last_action_message = msg
    st.session_state.last_action_type = msg_type


# ---------------------------------------------------------------------------
# Sidebar Navigation & Utilities
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🏋️ FitTrack System")
    st.caption("Gym Membership & Access Management")

    # Backend Status
    is_online = check_backend_health()
    if is_online:
        st.success("🟢 Backend Connected")
    else:
        st.error("🔴 Backend Offline")
        st.caption(f"Target URL: `{BACKEND_URL}`")

    st.divider()

    # System Date Configuration (defaults to current date, allows overriding for testing)
    st.subheader("📅 System Date")
    use_custom_date = st.checkbox("Override Date (Testing)", value=False)
    if use_custom_date:
        simulated_date = st.date_input("Simulation Date", value=date.today())
        system_today = simulated_date.isoformat()
        st.caption(f"Active simulated date: **{system_today}**")
    else:
        system_today = date.today().isoformat()
        st.caption(f"Current date: **{system_today}**")

    st.divider()

    # Navigation menu
    menu = st.radio(
        "Navigation",
        [
            "📊 Dashboard",
            "💳 Plans",
            "👤 Register Member",
            "👥 Members",
            "⏳ Expiring Soon",
            "🚪 Check-In",
            "🏋️ Trainers",
            "❄️ Freeze / Renew",
        ],
        index=0,
    )

    st.divider()

    # Demo Seed Button
    st.subheader("🧪 Quick Testing")
    if st.button("🌱 Seed Demo Data", use_container_width=True, disabled=not is_online):
        with st.spinner("Seeding demo data..."):
            res, err = api_call("POST", "/seed", params={"today": system_today})
            if err:
                set_flash_message(f"Seeding failed: {err}", "error")
            else:
                set_flash_message("Demo data seeded successfully with plans, trainers, and members!", "success")
            st.rerun()


# Display Flash Messages
if st.session_state.last_action_message:
    if st.session_state.last_action_type == "success":
        st.success(st.session_state.last_action_message)
    else:
        st.error(st.session_state.last_action_message)
    st.session_state.last_action_message = None


# ---------------------------------------------------------------------------
# View 1: Dashboard
# ---------------------------------------------------------------------------

if menu == "📊 Dashboard":
    st.header("📊 Gym Performance Dashboard")
    st.caption("Overview of membership counts, revenue, and daily facility activity.")

    if not is_online:
        st.error("Backend server is offline. Please start the backend service to view dashboard metrics.")
    else:
        # Date and period selector
        col_y, col_m, _ = st.columns([2, 2, 4])
        curr_d = date.fromisoformat(system_today)
        with col_y:
            selected_year = st.number_input("Year", min_value=2020, max_value=2035, value=curr_d.year, step=1)
        with col_m:
            selected_month = st.selectbox(
                "Month",
                options=list(range(1, 13)),
                index=curr_d.month - 1,
                format_func=lambda m: datetime(2000, m, 1).strftime("%B"),
            )

        # Fetch stats
        stats, err = api_call(
            "GET",
            "/dashboard",
            params={"year": selected_year, "month": selected_month, "today": system_today},
        )

        if err:
            st.error(f"Failed to load dashboard: {err}")
        elif stats:
            month_name = datetime(2000, selected_month, 1).strftime("%B")
            st.markdown(f"### Metrics for {month_name} {selected_year}")

            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric(
                    label=f"Revenue ({month_name})",
                    value=f"${stats['monthly_revenue']:,.2f}",
                )
            with m2:
                frozen_note = f"{stats['frozen_members']} frozen" if stats['frozen_members'] > 0 else "0 frozen"
                st.metric(
                    label="Active Members",
                    value=stats["active_members"],
                    delta=frozen_note,
                    delta_color="off",
                )
            with m3:
                st.metric(
                    label="Total Members",
                    value=stats["total_members"],
                )
            with m4:
                allowed_count = stats["today_checkins_allowed"]
                denied_count = stats["today_checkins_denied"]
                st.metric(
                    label="Today's Check-Ins",
                    value=stats["today_checkins_total"],
                    delta=f"{allowed_count} granted / {denied_count} blocked",
                    delta_color="normal" if denied_count == 0 else "inverse",
                )

            st.divider()

            # Expiring Soon Quick Peek
            st.subheader("⚠️ Urgent Attention: Members Expiring Within 7 Days")
            expiring, exp_err = api_call("GET", "/members/expiring-soon", params={"today": system_today})
            if exp_err:
                st.error(f"Could not check expiring members: {exp_err}")
            elif expiring:
                df_exp = pd.DataFrame(expiring)
                df_exp = df_exp[["id", "name", "phone", "plan_name", "end_date", "days_left"]]
                df_exp.columns = ["Member ID", "Name", "Phone", "Plan", "Expiry Date", "Days Remaining"]
                st.dataframe(df_exp, use_container_width=True, hide_index=True)
            else:
                st.info("No memberships expiring in the next 7 days.")


# ---------------------------------------------------------------------------
# View 2: Membership Plans
# ---------------------------------------------------------------------------

elif menu == "💳 Plans":
    st.header("💳 Membership Plans")
    st.caption("Manage gym membership plans, durations, and pricing.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Create New Plan")
        with st.form("create_plan_form", clear_on_submit=True):
            p_name = st.text_input("Plan Name*", placeholder="e.g. Gold Monthly")
            p_duration = st.number_input("Duration (Days)*", min_value=1, max_value=3650, value=30, step=1)
            p_price = st.number_input("Price ($)*", min_value=0.0, max_value=50000.0, value=49.99, step=5.0, format="%.2f")
            submitted = st.form_submit_button("Create Plan", use_container_width=True)

            if submitted:
                if not p_name.strip():
                    st.error("Plan name cannot be empty.")
                else:
                    payload = {"name": p_name.strip(), "duration_days": int(p_duration), "price": float(p_price)}
                    res, err = api_call("POST", "/plans", json_data=payload)
                    if err:
                        st.error(f"Failed to create plan: {err}")
                    else:
                        set_flash_message(f"Plan '{res['name']}' created successfully!")
                        st.rerun()

    with col2:
        st.subheader("Available Plans")
        plans, err = api_call("GET", "/plans")
        if err:
            st.error(f"Failed to load plans: {err}")
        elif plans:
            df_plans = pd.DataFrame(plans)[["id", "name", "duration_days", "price", "created_at"]]
            df_plans.columns = ["ID", "Plan Name", "Duration (Days)", "Price ($)", "Created At"]
            df_plans["Price ($)"] = df_plans["Price ($)"].map("${:,.2f}".format)
            st.dataframe(df_plans, use_container_width=True, hide_index=True)
        else:
            st.info("No plans created yet. Use the form on the left to create one.")


# ---------------------------------------------------------------------------
# View 3: Register Member
# ---------------------------------------------------------------------------

elif menu == "👤 Register Member":
    st.header("👤 Register New Member")
    st.caption("Enroll a new member, calculate membership duration, and record initial payment.")

    plans, err_p = api_call("GET", "/plans")
    trainers, err_t = api_call("GET", "/trainers")

    if not plans:
        st.warning("⚠️ No membership plans exist yet. Please create at least one plan before registering members.")
    else:
        with st.form("register_member_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                m_name = st.text_input("Full Name*", placeholder="e.g. John Doe")
                m_phone = st.text_input("Phone Number*", placeholder="e.g. 555-0199")

            with col_b:
                plan_options = {p["id"]: f"{p['name']} ({p['duration_days']} days - ${p['price']:,.2f})" for p in plans}
                selected_plan_id = st.selectbox(
                    "Membership Plan*",
                    options=list(plan_options.keys()),
                    format_func=lambda pid: plan_options[pid],
                )
                start_d = st.date_input("Start Date*", value=date.fromisoformat(system_today))

            # Trainer selection
            trainer_options = {0: "None (No assigned trainer)"}
            if trainers:
                for t in trainers:
                    trainer_options[t["id"]] = f"{t['name']} - {t['specialty']}"
            selected_trainer_id = st.selectbox(
                "Assign Trainer (Optional)",
                options=list(trainer_options.keys()),
                format_func=lambda tid: trainer_options[tid],
            )

            submit_member = st.form_submit_button("Register & Process Payment", use_container_width=True)

            if submit_member:
                if not m_name.strip() or not m_phone.strip():
                    st.error("Please provide both name and phone number.")
                else:
                    payload = {
                        "name": m_name.strip(),
                        "phone": m_phone.strip(),
                        "plan_id": selected_plan_id,
                        "start_date": start_d.isoformat(),
                        "trainer_id": selected_trainer_id if selected_trainer_id > 0 else None,
                    }
                    res, err = api_call("POST", "/members", json_data=payload)
                    if err:
                        st.error(f"Registration failed: {err}")
                    else:
                        set_flash_message(
                            f"Member registered successfully! ID: #{res['id']} | Name: {res['name']} | "
                            f"Valid: {res['start_date']} to {res['end_date']}."
                        )
                        st.rerun()


# ---------------------------------------------------------------------------
# View 4: Members Directory
# ---------------------------------------------------------------------------

elif menu == "👥 Members":
    st.header("👥 Members Directory")
    st.caption("View and manage all registered gym members.")

    members, err = api_call("GET", "/members", params={"today": system_today})
    if err:
        st.error(f"Failed to load members: {err}")
    elif members:
        search_term = st.text_input("🔍 Search members by name or phone:", placeholder="Type to filter...")

        filtered = members
        if search_term.strip():
            st_lower = search_term.strip().lower()
            filtered = [
                m for m in members
                if st_lower in m["name"].lower() or st_lower in m["phone"].lower() or st_lower in str(m["id"])
            ]

        if filtered:
            display_data = []
            for m in filtered:
                if m["is_frozen"]:
                    status_badge = "❄️ Frozen"
                elif m["is_active"]:
                    status_badge = "🟢 Active"
                else:
                    status_badge = "🔴 Expired"

                display_data.append({
                    "ID": m["id"],
                    "Name": m["name"],
                    "Phone": m["phone"],
                    "Plan": m.get("plan_name") or f"Plan #{m['plan_id']}",
                    "Trainer": m.get("trainer_name") or "None",
                    "Start Date": m["start_date"],
                    "End Date": m["end_date"],
                    "Status": status_badge,
                    "Total Frozen Days": m["total_frozen_days"],
                })

            st.dataframe(pd.DataFrame(display_data), use_container_width=True, hide_index=True)
        else:
            st.info("No members match your search criteria.")

        st.divider()

        # Quick Trainer Assignment Section
        st.subheader("🏋️ Assign or Change Trainer")
        trainers, _ = api_call("GET", "/trainers")
        trainer_dict = {0: "Unassign (No Trainer)"}
        if trainers:
            for t in trainers:
                trainer_dict[t["id"]] = f"{t['name']} ({t['specialty']})"

        with st.form("assign_trainer_form"):
            col_m_pick, col_t_pick, col_btn = st.columns([2, 2, 1])
            with col_m_pick:
                member_options = {m["id"]: f"#{m['id']} - {m['name']} (Currently: {m.get('trainer_name') or 'None'})" for m in members}
                target_member_id = st.selectbox("Select Member", options=list(member_options.keys()), format_func=lambda x: member_options[x])
            with col_t_pick:
                target_trainer_id = st.selectbox("Select Trainer", options=list(trainer_dict.keys()), format_func=lambda x: trainer_dict[x])
            with col_btn:
                st.write("")
                st.write("")
                assign_btn = st.form_submit_button("Update Trainer", use_container_width=True)

            if assign_btn:
                t_val = target_trainer_id if target_trainer_id > 0 else None
                res, err_assign = api_call("PUT", f"/members/{target_member_id}/trainer", json_data={"trainer_id": t_val})
                if err_assign:
                    st.error(f"Failed to update trainer: {err_assign}")
                else:
                    set_flash_message(f"Trainer updated for member #{target_member_id}!")
                    st.rerun()
    else:
        st.info("No members registered yet. Use 'Register Member' or 'Seed Demo Data' to get started.")


# ---------------------------------------------------------------------------
# View 5: Expiring Soon
# ---------------------------------------------------------------------------

elif menu == "⏳ Expiring Soon":
    st.header("⏳ Expiring Soon (Next 7 Days)")
    st.caption("Members whose access expires between today and today + 7 days.")

    expiring, err = api_call("GET", "/members/expiring-soon", params={"today": system_today})
    if err:
        st.error(f"Failed to fetch expiring members: {err}")
    elif expiring:
        st.warning(f"⚠️ {len(expiring)} membership(s) require renewal attention!")

        df_exp = pd.DataFrame(expiring)
        df_exp = df_exp[["id", "name", "phone", "plan_name", "end_date", "days_left"]]
        df_exp.columns = ["Member ID", "Full Name", "Phone", "Current Plan", "Expiration Date", "Days Left"]
        st.dataframe(df_exp, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("🔄 Quick Renewal for Expiring Member")
        plans, _ = api_call("GET", "/plans")
        if plans:
            exp_member_options = {m["id"]: f"#{m['id']} - {m['name']} ({m['days_left']} days left)" for m in expiring}
            plan_options = {p["id"]: f"{p['name']} ({p['duration_days']} days - ${p['price']:,.2f})" for p in plans}

            with st.form("quick_renew_form"):
                col_m_renew, col_p_renew = st.columns(2)
                with col_m_renew:
                    q_mid = st.selectbox("Select Member to Renew", options=list(exp_member_options.keys()), format_func=lambda x: exp_member_options[x])
                with col_p_renew:
                    q_pid = st.selectbox("Select Plan", options=list(plan_options.keys()), format_func=lambda x: plan_options[x])

                renew_submit = st.form_submit_button("Renew Membership & Process Payment", use_container_width=True)

                if renew_submit:
                    res, r_err = api_call(
                        "POST",
                        f"/members/{q_mid}/renew",
                        json_data={"plan_id": q_pid, "renewal_date": system_today},
                        params={"today": system_today},
                    )
                    if r_err:
                        st.error(f"Renewal failed: {r_err}")
                    else:
                        set_flash_message(
                            f"Membership for Member #{q_mid} renewed successfully until {res['new_end_date']}! "
                            f"Payment of ${res['amount_paid']:,.2f} recorded."
                        )
                        st.rerun()
    else:
        st.success("✅ No memberships are expiring within the next 7 days.")


# ---------------------------------------------------------------------------
# View 6: Daily Check-In
# ---------------------------------------------------------------------------

elif menu == "🚪 Check-In":
    st.header("🚪 Front Desk Check-In")
    st.caption("Record and validate member daily facility check-in.")

    # Show persistent checkin result banner if available
    if st.session_state.checkin_result:
        res = st.session_state.checkin_result
        if res["allowed"]:
            name = res.get("member_name") or f"Member #{res.get('member_id')}"
            st.success(f"### ✅ Access Granted: Welcome, {name}!\nCheck-in recorded at {res['check_in_time']}.")
        else:
            reason = res.get("reason", "Unknown verification error")
            st.error(f"### ⛔ Access Denied: {reason}")
        if st.button("Dismiss Status Banner"):
            st.session_state.checkin_result = None
            st.rerun()

    st.write("")

    col_in, col_hist = st.columns([1, 1])

    with col_in:
        st.subheader("Member Check-In Form")
        with st.form("check_in_form", clear_on_submit=False):
            member_id_input = st.number_input(
                "Enter Member ID*",
                min_value=1,
                max_value=999999,
                step=1,
                help="Enter the numeric member ID or scan the member card",
            )
            chk_date = st.date_input("Check-In Date", value=date.fromisoformat(system_today))
            submit_checkin = st.form_submit_button("Verify & Check In", use_container_width=True)

            if submit_checkin:
                payload = {
                    "member_id": int(member_id_input),
                    "check_in_date": chk_date.isoformat(),
                }
                res, err = api_call("POST", "/check-ins", json_data=payload)
                if err:
                    st.error(f"Check-in request error: {err}")
                else:
                    st.session_state.checkin_result = res
                    st.rerun()

    with col_hist:
        st.subheader("Today's Recent Activity")
        checkins, err_chk = api_call("GET", "/check-ins", params={"limit": 15})
        if err_chk:
            st.error(f"Could not load check-in log: {err_chk}")
        elif checkins:
            rows = []
            for c in checkins:
                rows.append({
                    "Time": c["check_in_time"][-8:],
                    "Member": c.get("member_name") or f"ID #{c['attempted_member_id']}",
                    "Status": "✅ Granted" if c["allowed"] else "⛔ Denied",
                    "Reason": c.get("reason") or "Access Granted",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No check-ins recorded yet.")


# ---------------------------------------------------------------------------
# View 7: Trainers
# ---------------------------------------------------------------------------

elif menu == "🏋️ Trainers":
    st.header("🏋️ Personal Trainers Management")
    st.caption("Manage trainers, view assigned members, and monitor capacity.")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Add New Trainer")
        with st.form("create_trainer_form", clear_on_submit=True):
            t_name = st.text_input("Trainer Name*", placeholder="e.g. Alex Rivera")
            t_phone = st.text_input("Phone Number*", placeholder="e.g. 555-0155")
            t_specialty = st.text_input("Specialty*", placeholder="e.g. Strength & Conditioning")
            submitted = st.form_submit_button("Add Trainer", use_container_width=True)

            if submitted:
                if not t_name.strip() or not t_phone.strip() or not t_specialty.strip():
                    st.error("All trainer fields are required.")
                else:
                    payload = {"name": t_name.strip(), "phone": t_phone.strip(), "specialty": t_specialty.strip()}
                    res, err = api_call("POST", "/trainers", json_data=payload)
                    if err:
                        st.error(f"Failed to create trainer: {err}")
                    else:
                        set_flash_message(f"Trainer '{res['name']}' added successfully!")
                        st.rerun()

    with col2:
        st.subheader("Registered Trainers")
        trainers, err = api_call("GET", "/trainers")
        if err:
            st.error(f"Failed to load trainers: {err}")
        elif trainers:
            df_trainers = pd.DataFrame(trainers)[["id", "name", "phone", "specialty", "member_count"]]
            df_trainers.columns = ["ID", "Name", "Phone", "Specialty", "Assigned Members"]
            st.dataframe(df_trainers, use_container_width=True, hide_index=True)
        else:
            st.info("No trainers registered yet.")

    st.divider()

    # Trainer's Members drill-down
    if trainers:
        st.subheader("📋 View Assigned Members by Trainer")
        t_dict = {t["id"]: f"{t['name']} ({t['specialty']}) - {t['member_count']} member(s)" for t in trainers}
        selected_tid = st.selectbox("Select Trainer to view roster:", options=list(t_dict.keys()), format_func=lambda x: t_dict[x])

        members_assigned, err_assigned = api_call("GET", f"/trainers/{selected_tid}/members")
        if err_assigned:
            st.error(f"Failed to load roster: {err_assigned}")
        elif members_assigned:
            df_m = pd.DataFrame(members_assigned)[["id", "name", "phone", "plan_name", "start_date", "end_date"]]
            df_m.columns = ["Member ID", "Name", "Phone", "Plan", "Start Date", "End Date"]
            st.dataframe(df_m, use_container_width=True, hide_index=True)
        else:
            st.info("This trainer currently has no assigned members.")


# ---------------------------------------------------------------------------
# View 8: Freeze / Renew
# ---------------------------------------------------------------------------

elif menu == "❄️ Freeze / Renew":
    st.header("❄️ Membership Freeze & 🔄 Renewal")
    st.caption("Temporarily freeze active memberships or renew expiring/expired memberships.")

    tab_freeze, tab_renew = st.tabs(["❄️ Freeze Membership", "🔄 Renew Membership"])

    members, err_m = api_call("GET", "/members", params={"today": system_today})

    with tab_freeze:
        st.subheader("Freeze Membership")
        st.markdown(
            """
            - **Rules:** Freeze duration is between **1 and 30 days**.
            - **Lifetime Cap:** Maximum **30 cumulative days** of freeze per membership.
            - **Effect:** Extends membership expiry date by the frozen days and temporarily blocks facility check-ins.
            """
        )

        if not members:
            st.info("No members available to freeze.")
        else:
            # Dropdown of members
            freeze_opts = {
                m["id"]: f"#{m['id']} - {m['name']} (End: {m['end_date']} | Frozen: {m['total_frozen_days']}/30 days used)"
                for m in members
            }
            with st.form("freeze_form"):
                f_mid = st.selectbox("Select Member*", options=list(freeze_opts.keys()), format_func=lambda x: freeze_opts[x])
                f_member = next((m for m in members if m["id"] == f_mid), None)
                used = f_member["total_frozen_days"] if f_member else 0
                remaining = max(0, 30 - used)

                st.caption(f"Member has used **{used} days** of freeze. **{remaining} days** remaining.")

                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    f_days = st.number_input("Days to Freeze (1-30)*", min_value=1, max_value=30, value=min(7, remaining or 1), step=1)
                with col_f2:
                    f_start = st.date_input("Freeze Start Date*", value=date.fromisoformat(system_today))

                f_reason = st.text_input("Reason for Freeze", placeholder="e.g. Travel, medical, personal")
                submit_freeze = st.form_submit_button("Apply Membership Freeze", use_container_width=True)

                if submit_freeze:
                    payload = {
                        "days": int(f_days),
                        "start_date": f_start.isoformat(),
                        "reason": f_reason.strip() if f_reason else None,
                    }
                    res, err_f = api_call("POST", f"/members/{f_mid}/freeze", json_data=payload, params={"today": system_today})
                    if err_f:
                        st.error(f"Freeze request failed: {err_f}")
                    else:
                        set_flash_message(
                            f"Freeze applied successfully for {res['days']} days! "
                            f"Freeze period: {res['start_date']} to {res['end_date']}. "
                            f"New membership expiry date: {res['new_membership_end_date']}."
                        )
                        st.rerun()

    with tab_renew:
        st.subheader("Renew Membership")
        st.markdown(
            """
            - **Still Active:** Extends from the current `end_date` by the plan duration.
            - **Expired:** Extends from today (inclusive) by the plan duration.
            - **Payment:** Automatically logs a new payment for revenue accuracy.
            """
        )

        plans, err_p = api_call("GET", "/plans")
        if not members or not plans:
            st.info("Members and plans are required to process renewals.")
        else:
            renew_member_opts = {
                m["id"]: f"#{m['id']} - {m['name']} (Expires/Expired: {m['end_date']}) - Current Plan: {m.get('plan_name')}"
                for m in members
            }
            renew_plan_opts = {
                p["id"]: f"{p['name']} ({p['duration_days']} days - ${p['price']:,.2f})"
                for p in plans
            }

            with st.form("renew_form"):
                r_mid = st.selectbox("Select Member to Renew*", options=list(renew_member_opts.keys()), format_func=lambda x: renew_member_opts[x])
                r_pid = st.selectbox("Renewal Plan*", options=list(renew_plan_opts.keys()), format_func=lambda x: renew_plan_opts[x])
                r_date = st.date_input("Renewal Date*", value=date.fromisoformat(system_today))

                submit_renew = st.form_submit_button("Process Renewal & Record Payment", use_container_width=True)

                if submit_renew:
                    payload = {
                        "plan_id": int(r_pid),
                        "renewal_date": r_date.isoformat(),
                    }
                    res, err_r = api_call("POST", f"/members/{r_mid}/renew", json_data=payload, params={"today": system_today})
                    if err_r:
                        st.error(f"Renewal failed: {err_r}")
                    else:
                        set_flash_message(
                            f"Renewal complete for Member #{res['member_id']}! "
                            f"New expiry date: {res['new_end_date']}. "
                            f"Payment of ${res['amount_paid']:,.2f} recorded on {res['payment_date']}."
                        )
                        st.rerun()
