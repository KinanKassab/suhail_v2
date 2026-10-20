# Suhail v2 — Suhail Research Simulator

A responsive Flask project for simulating a 5-variable differential-equation system using SciPy LSODA, with chart rendering and saved experiments plus PDF reports.

> **Critical warning:** this is an **exploratory mathematical model that has not been clinically validated**. It is not suitable for diagnosis, forecasting a real tumor outcome, adjusting treatment, or calibrating drug doses. The coefficients are hypothetical. Do not use real patient data on the demo service or free database tiers. No independent validation of the equations or their assignment to individuals or institutions is included in this project.

## Files

```text
suhail_v2/
├── app.py                 # Flask pages, API, and auth
├── model.py               # 5-state ODE system
├── calibration.py         # 5 research calibration coefficients
├── validation.py          # Pydantic input validation
├── database.py            # PostgreSQL or SQLite
├── pdf_export.py          # WeasyPrint PDF
├── requirements.txt
├── Dockerfile
├── render.yaml            # Free Render trial only for demo database usage
├── render-production.yaml # Example production setup with persistent database
├── .env.example
├── .gitignore
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── index.html
│   ├── inputs.html
│   ├── history.html
│   ├── view.html
│   └── report.html
├── static/css/style.css
├── static/js/main.js
└── tests/
    ├── test_model.py
    └── test_web.py
```

## Deploying on Render from GitHub (recommended)

1. Unzip the project and upload the **contents** of the `suhail_v2` folder to a private GitHub repository. Do not upload `.env` or `instance/` files.
2. In https://dashboard.render.com/ choose **New → Blueprint** and connect the repo containing `render.yaml`.
3. The app `suhail-v2` and database `suhail-db` will appear; `render.yaml` uses a free Web Service and free Postgres **for temporary experiments only**.
4. When prompted for `ADMIN_PASSWORD`, enter a strong unique admin password; `SECRET_KEY` is generated automatically. Do not save it in GitHub files.
5. Start the Blueprint app, then open the link `https://<your-service>.onrender.com` and log in.
6. Test the `/healthz` route, create a simulation, then open the history view and try downloading a PDF.

**Important:** the free Render Postgres database expires after 30 days with a 14-day upgrade window and has no backups. Therefore `render.yaml` is not suitable for long-term history retention. For persistent data, use a paid database or external PostgreSQL. The project includes a paid template named `render-production.yaml`; rename it to `render.yaml` before linking if you want this plan. Check Render pricing before starting a paid plan. Plan details may change.

### Alternative: New Web Service (without Blueprint)

- Choose `Docker` as the runtime and the repo containing the Dockerfile.
- Set `SECRET_KEY`, `ADMIN_PASSWORD`, and `PRODUCTION=1`.
- Set `DATABASE_URL` to a PostgreSQL connection if you want the simulation history to persist.
- If `DATABASE_URL` is not supplied, SQLite will be used inside the container **and data will be lost after redeploying or restarting the instance** because of ephemeral storage on Render. This mode is only suitable for testing the interface with synthetic cases.
- The Dockerfile runs Gunicorn automatically and listens on `0.0.0.0:$PORT`, so no extra Start Command is needed.

## Local run

Docker installs the system requirements for WeasyPrint and Arabic fonts automatically:

```bash
docker build -t suhail-v2 .
docker run --rm -p 5000:10000 \
  -e PORT=10000 \
  -e PRODUCTION=1 \
  -e SECRET_KEY='replace-with-a-long-random-secret' \
  -e ADMIN_PASSWORD='replace-with-a-strong-password' \
  suhail-v2
```

Open http://localhost:5000 and enter the password.

To run Python locally outside Docker (Python 3.11 preferred):

```bash
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env         # Windows: copy .env.example .env
# edit the values in .env
python app.py
```

Warning: the operating system requires the Pango, Fontconfig, and Arabic font libraries to export PDFs. Docker is therefore easier and more consistent.

## Automated verification

```bash
pip install pytest
pytest -q
```

The `test_web.py` checks cover authentication, CSRF, `/simulate` calls, reading results, PDF export, and handling invalid input errors. The numerical solution properties are tested in `test_model.py`.

## API

`POST /simulate` requires a logged-in session, a CSRF token from the `meta[name="csrf-token"]` tag sent in the `X-CSRF-Token` header, and JSON data.

Example:

```json
{
  "patient_name": "Demo case 01",
  "patient_id": "DEMO-001",
  "S0": 5000,
  "R0": 100,
  "I0": 0.5,
  "calibration_mode": "manual",
  "sigma_C": 0.5,
  "sigma_L": 0.5,
  "sigma_I": 0.5,
  "SRF": 0.5,
  "sigma_A": 0.25,
  "T_days": 30,
  "dose_days": [1, 8, 15, 22],
  "dose_amount": 0.04
}
```

The response returns the simulation ID `id`, the result page URL `url`, the PDF URL `pdf_url`, and time-series arrays for plotting.

## Changes from the submitted files

- Completed `app.py` after the truncated section at `results["recommendations"] = _gen`; replaced medical recommendations with documented methodological limits.
- Corrected the `σ_A` input inside the logistic capacity bound.
- Applied `T_eff = T × SRF` as specified by the equation instead of `T × (0.5 + SRF)` from the old script.
- Solved the equations separately for each day to reduce integration error across discontinuous dosing boundaries.
- Added manual calibration selection that **respects entered values** or a warning-only derived calibration.
- Validated dose days after `T_days` in Pydantic instead of relying on field order.
- Added local SQLite and automatic PostgreSQL handling via `DATABASE_URL`.
- Removed default secrets in production and added login, CSRF, history, and PDF protection.
- Sent PDFs directly without creating report files in the shared folder.

## Important scientific cautions

1. The supplied S equation includes a transition proportional to `T_eff * S * S/(S+R)`, while the R equation adds `T_eff * S`, so the transition does **not conserve total cell count**. The original formulas were kept to align with the research ask, but they should be audited before any scientific use.
2. The equation describes the effect of `σ_C` both inside the drug concentration and again after calculating `E_drug`, which duplicates the calibration effect; this design requires scientific review.
3. Deriving `σ_C` from PSA drop and using Gleason plus CD8/CD4/NK and diet/sleep/activity values creates hypothetical equations that are **not validated for treatment efficacy**.
4. `TR` is a scaled resistance index, not the observed fraction of resistant cells. That is why `resistance_fraction=R/(S+R)` was added as a separate output, and `TG` is an index rather than a true tumor-volume measurement.
5. The original code names coefficients as `day⁻¹` or dimensionless, even though several parameters require other units for consistency; the measurements need to be standardized and compared against appropriate data.
6. The five-state system collapses drug distribution and absorption. The exponential drug absorption input per dosing day was retained, but it does not represent validated pharmacokinetics.

## Privacy and production

The single-admin version with a shared password is suitable only for a protected demo environment, **not a production-ready patient-file platform**. If real medical data will be used, you need a specialized security and privacy review, per-user access controls, audit logs, key management, retention and deletion policy, encryption and backups, and appropriate legal compliance. Synthetic data is recommended here.
