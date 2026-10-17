import math
import pytest
from model import SuhailModel, SimulationConfig, DynamicConstants
from calibration import SuhailCalibration, compute_sigma_C, compute_SRF
from validation import SimulationRequest


def test_default_model_has_all_days_and_finite_values():
    history = SuhailModel(SimulationConfig()).run()["history"]
    assert len(history) == 31
    assert [h["day"] for h in history] == list(range(31))
    for h in history:
        assert all(math.isfinite(v) for v in h.values())
        assert h["S"] >= 0 and h["R"] >= 0 and h["C_plasma"] >= 0
        assert 0 <= h["I"] <= 1 and 0 <= h["f_R"] <= 1
        assert 0 <= h["resistance_fraction"] <= 1


def test_drug_concentration_after_dose():
    history = SuhailModel(SimulationConfig(T_days=3, dose_days=[1])).run()["history"]
    assert history[0]["C_plasma"] == 0
    assert history[1]["C_plasma"] > 0
    assert history[3]["C_plasma"] < history[1]["C_plasma"]


def test_sigma_A_changes_growth():
    constants = DynamicConstants(K_cells=10000, G_S=0.2, I_s=0,
                                I_r=0, N_G_I=0, T=0)
    low = SuhailModel(SimulationConfig(S0=5000,R0=1,T_days=3,dose_days=[1],
                      dose_amount=0.000001,calibration=SuhailCalibration(sigma_A=0),
                      constants=constants)).run()["history"]
    high = SuhailModel(SimulationConfig(S0=5000,R0=1,T_days=3,dose_days=[1],
                      dose_amount=0.000001,calibration=SuhailCalibration(sigma_A=1),
                      constants=constants)).run()["history"]
    assert low[-1]["S"] > high[-1]["S"]


def test_reject_invalid_dose_day():
    with pytest.raises(ValueError):
        SimulationRequest(T_days=5, dose_days=[1, 8])


def test_reject_non_finite_values():
    with pytest.raises(ValueError):
        SimulationRequest(S0=float('nan'))


def test_srf_zero_baseline_must_be_manual():
    with pytest.raises(ValueError):
        compute_SRF(0, 10)


def test_psa_expected_must_be_positive():
    with pytest.raises(ValueError):
        compute_sigma_C(0.5, 0)


def test_manual_calibration_values_are_kept():
    from app import make_calibration
    req = SimulationRequest(sigma_C=.9, sigma_L=.1, sigma_I=.8,
                            SRF=.4, sigma_A=.7)
    cal = make_calibration(req)
    assert cal.sigma_C == .9 and cal.sigma_A == .7
