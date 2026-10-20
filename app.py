"""Suhail v2 – research simulation dashboard; no clinical use."""
import hmac
import logging
import os
import secrets
from datetime import timedelta
from functools import wraps

from dotenv import load_dotenv
from flask import (Flask, abort, jsonify, make_response, redirect, render_template,
                   request, send_file, session, url_for)
from pydantic import ValidationError
from io import BytesIO

from calibration import (SuhailCalibration, compute_sigma_A, compute_sigma_C,
                         compute_sigma_I, compute_sigma_L, compute_SRF)
from model import DynamicConstants, SimulationConfig, SuhailModel
from validation import SimulationRequest
import database as db
from pdf_export import generate_pdf

load_dotenv()
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
IS_HOSTED = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL") or
                 os.environ.get("PRODUCTION") == "1")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
if IS_HOSTED and (not os.getenv("SECRET_KEY") or not ADMIN_PASSWORD):
    raise RuntimeError("Production requires SECRET_KEY and ADMIN_PASSWORD")
app.config.update(
    SECRET_KEY=os.getenv("SECRET_KEY", "development-only-unsafe-key"),
    MAX_CONTENT_LENGTH=128 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_HOSTED,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
db.init_db()


def _csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


@app.context_processor
def inject_helpers():
    return {"csrf_token": _csrf(), "auth_enabled": bool(ADMIN_PASSWORD)}


def csrf_ok():
    sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    return hmac.compare_digest(str(sent), str(session.get("csrf_token", ""))) and bool(sent)


def require_auth(route):
    @wraps(route)
    def wrapped(*args, **kwargs):
        if ADMIN_PASSWORD and not session.get("authenticated"):
            if request.path == "/simulate":
                return jsonify(error="Please log in"), 401
            return redirect(url_for("login"))
        return route(*args, **kwargs)
    return wrapped


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz():
    return jsonify(status="ok")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD:
        return redirect(url_for("index"))
    if request.method == "POST":
        if not csrf_ok():
            abort(400)
        password = request.form.get("password", "")
        if hmac.compare_digest(password, ADMIN_PASSWORD):
            session.clear()
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("index"))
        return render_template("login.html", error="Incorrect password"), 401
    return render_template("login.html")


@app.post("/logout")
def logout():
    if not csrf_ok():
        abort(400)
    session.clear()
    return redirect(url_for("login" if ADMIN_PASSWORD else "index"))


@app.get("/")
@require_auth
def index():
    return render_template("index.html")


@app.get("/inputs")
@require_auth
def inputs_page():
    return render_template("inputs.html")


@app.get("/history")
@require_auth
def history_page():
    return render_template("history.html", sims=db.list_simulations())


@app.get("/view/<int:sim_id>")
@require_auth
def view_simulation(sim_id):
    rec = db.get_simulation(sim_id)
    if not rec:
        abort(404)
    return render_template("view.html", rec=rec, results=rec["results"])


@app.get("/report/<int:sim_id>")
@require_auth
def report_page(sim_id):
    rec = db.get_simulation(sim_id)
    if not rec:
        abort(404)
    return render_template("report.html", rec=rec, results=rec["results"])


@app.get("/pdf/<int:sim_id>")
@require_auth
def export_pdf(sim_id):
    rec = db.get_simulation(sim_id)
    if not rec:
        abort(404)
    try:
        pdf = generate_pdf(rec)
    except Exception:
        app.logger.exception("PDF generation failed")
        return "PDF file could not be generated", 500
    return send_file(BytesIO(pdf), mimetype="application/pdf", as_attachment=True,
                     download_name=f"suhail-report-{sim_id}.pdf")


def make_calibration(req):
    if req.calibration_mode == "manual":
        return SuhailCalibration(req.sigma_C, req.sigma_L, req.sigma_I,
                                 req.SRF, req.sigma_A)
    return SuhailCalibration(
        sigma_C=compute_sigma_C(req.psa_actual, req.psa_expected),
        sigma_L=compute_sigma_L(req.protein, req.sugar, req.sleep_h, req.activity_min),
        sigma_I=compute_sigma_I(req.cd8, req.cd4, req.nk,
                                req.ref_cd8, req.ref_cd4, req.ref_nk),
        SRF=compute_SRF(req.R0, req.R1),
        sigma_A=compute_sigma_A(req.gleason),
    )


def summarize(history, calibration):
    initial, final = history[0], history[-1]

    def pct(a, b):
        return None if abs(a) < 1e-12 else (b - a) / a * 100.0

    return {
        "S0": initial["S"], "R0": initial["R"],
        "S_final": final["S"], "R_final": final["R"], "I_final": final["I"],
        "S_change_pct": pct(initial["S"], final["S"]),
        "R_change_pct": pct(initial["R"], final["R"]),
        "total_initial": initial["total_cells"], "total_final": final["total_cells"],
        "total_change_pct": pct(initial["total_cells"], final["total_cells"]),
        "resistance_initial": initial["resistance_fraction"],
        "resistance_final": final["resistance_fraction"],
        "TG_initial": initial["TG"], "TG_final": final["TG"],
        "TG_change_pct": pct(initial["TG"], final["TG"]),
        "sample_5days": [h for h in history if h["day"] % 5 == 0 or h is final],
        "calibration_used": calibration.to_dict(),
        "chart": {key: [h[key] for h in history]
                  for key in ("day", "S", "R", "I", "f_R", "C_eff", "E_drug",
                              "total_cells", "resistance_fraction", "TR", "TG")},
        "notices": [
            "This is an exploratory mathematical model that has not been clinically validated and should not be used for diagnosis or treatment selection.",
            "Default calibration constants and factors are assumed; PSA is not a direct measure of drug efficacy.",
            "The S-to-R transition in the supplied equations does not conserve total cell count.",
            "TG is a mathematical resistance-derived index, not a clinical measure of tumor size.",
        ],
    }


@app.post("/simulate")
@require_auth
def simulate():
    if not csrf_ok():
        return jsonify(error="CSRF validation failed. Please refresh the page."), 403
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="Please send valid JSON data"), 400
    try:
        req = SimulationRequest.model_validate(payload)
        cal = make_calibration(req)
        constants = DynamicConstants(G_S=req.G_S, G_R=req.G_R, T=req.T,
                                     I_s=req.I_s, I_r=req.I_r,
                                     C_G_I=req.C_G_I, N_G_I=req.N_G_I,
                                     K_cells=req.K_cells)
        config = SimulationConfig(S0=req.S0, R0=req.R0, I0=req.I0,
                                  dose_days=req.dose_days, dose_amount=req.dose_amount,
                                  T_days=req.T_days, calibration=cal, constants=constants)
        history = SuhailModel(config).run()["history"]
        results = summarize(history, cal)
    except ValidationError as exc:
        return jsonify(error="Input is invalid", details=[{"field": ".".join(map(str, e["loc"])),
                        "message": e["msg"]} for e in exc.errors()]), 400
    except (ValueError, OverflowError) as exc:
        return jsonify(error=str(exc)), 400
    except Exception:
        app.logger.exception("Simulation computation error")
        return jsonify(error="An error occurred during the simulation"), 500
    try:
        sim_id = db.save_simulation(req, results)
    except Exception:
        app.logger.exception("Database insertion failed")
        return jsonify(error="The simulation completed, but saving the data failed"), 500
    return jsonify(id=sim_id, url=url_for("view_simulation", sim_id=sim_id),
                   pdf_url=url_for("export_pdf", sim_id=sim_id), results=results)


@app.errorhandler(413)
def too_large(err):
    return jsonify(error="Request payload is too large"), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
