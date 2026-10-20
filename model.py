"""Five-state experimental ODE simulator. NOT for clinical prediction or treatment.

S, R are abstract modeled cell populations, I in [0,1], f_R in [0,1],
C_plasma in arbitrary concentration units consistent with EC50 and dose_amount.
The empirical coefficients and equations have not been independently validated.
"""
from dataclasses import dataclass, field
from typing import List
import numpy as np
from scipy.integrate import solve_ivp
from calibration import SuhailCalibration


@dataclass
class DynamicConstants:
    G_S: float = 0.05
    G_R: float = 0.03
    T: float = 0.01
    I_s: float = 0.3
    I_r: float = 0.2
    C_G_I: float = 0.4
    N_G_I: float = 0.3
    ME: float = 0.001
    G_T_G_I: float = 0.0001
    K_immune: float = 1000.0
    K_T: float = 1000.0
    I_max: float = 1.0
    E_max: float = 1.0
    EC50: float = 0.05
    n_hill: float = 1.5
    k_elim: float = 0.15
    k_abs: float = 2.0
    K_partition: float = 0.8
    k_on: float = 1.0
    k_off: float = 0.5
    f_R0: float = 0.0
    K_cells: float = 1e9


@dataclass
class SimulationConfig:
    S0: float = 5000.0
    R0: float = 100.0
    I0: float = 0.5
    dose_days: List[int] = field(default_factory=lambda: [1, 8, 15, 22])
    dose_amount: float = 0.04
    T_days: int = 30
    calibration: SuhailCalibration = field(default_factory=SuhailCalibration)
    constants: DynamicConstants = field(default_factory=DynamicConstants)


class SuhailModel:
    def __init__(self, config: SimulationConfig):
        self.cfg = config
        self.c = config.constants
        self.cal = config.calibration
        self.cal.validate()
        if self.c.K_cells <= 0 or self.c.EC50 <= 0 or self.c.I_max <= 0:
            raise ValueError("Capacity, EC50, and immune constants must be positive")
        if self.cfg.T_days < 1 or not self.cfg.dose_days:
            raise ValueError("Simulation duration and dose days are invalid")
        if any(d < 1 or d > self.cfg.T_days for d in self.cfg.dose_days):
            raise ValueError("Dose days fall outside the simulation window")

    def _hill(self, x):
        x = max(float(x), 0.0)
        return x ** self.c.n_hill / (x ** self.c.n_hill + self.c.EC50 ** self.c.n_hill)

    def _dose_input(self, t, day):
        # Finite 24-h absorption window, reset at each dosing day.
        if day not in self.cfg.dose_days:
            return 0.0
        return self.cfg.dose_amount * self.c.k_abs * np.exp(-self.c.k_abs * (t - day + 1))

    def _system(self, t, y, day):
        S, R, I, f_R, C_plasma = y
        c, cal = self.c, self.cal
        S, R, C_plasma = max(S, 0.0), max(R, 0.0), max(C_plasma, 0.0)
        I, f_R = float(np.clip(I, 0, c.I_max)), float(np.clip(f_R, 0, 1))
        N = S + R
        C_eff = C_plasma * c.K_partition * cal.sigma_C
        E_drug = c.E_max * self._hill(C_eff) * f_R
        I_eff = I * cal.sigma_I
        L_eff = cal.sigma_L * 0.1
        T_eff = c.T * cal.SRF   # Matching the provided equation, not T*(0.5+SRF)
        carrying = 1.0 - cal.sigma_A * N / c.K_cells  # σ_A was omitted in original code
        # The originally supplied S-loss and R-gain terms are not mass-conserving.
        # Retained here for mathematical fidelity; interpretation remains exploratory.
        dS = S * (c.G_S * carrying - I_eff * c.I_s -
                  T_eff * S / (N + 1e-12) - L_eff - E_drug * cal.sigma_C)
        dR = R * (c.G_R * carrying - I_eff * c.I_r - L_eff) + T_eff * S
        dI = (c.ME * N / (N + c.K_immune) - c.C_G_I * E_drug +
              c.N_G_I * cal.sigma_L + c.G_T_G_I * N / (N + c.K_T)) * (1 - I / c.I_max)
        if I <= 0 and dI < 0:
            dI = 0.0
        df_R = c.k_on * C_eff * (1 - f_R) - c.k_off * f_R
        dC = -c.k_elim * C_plasma + self._dose_input(t, day)
        return np.array([dS, dR, dI, df_R, dC], dtype=float)

    def _snapshot(self, day, y):
        S, R, I, f_R, C_plasma = [float(v) for v in y]
        c, cal = self.c, self.cal
        S, R, C_plasma = max(0, S), max(0, R), max(0, C_plasma)
        I, f_R = float(np.clip(I, 0, c.I_max)), float(np.clip(f_R, 0, 1))
        C_eff = C_plasma * c.K_partition * cal.sigma_C
        E_drug = c.E_max * self._hill(C_eff) * f_R
        base_ratio = R / (S + R + 1e-12)
        # TR: experimental adjusted resistance index; NOT actual resistance fraction.
        TR = float(np.clip(base_ratio * (0.5 + cal.SRF) * (0.5 + cal.sigma_A), 0, 1))
        return dict(day=day, S=S, R=R, I=I, f_R=f_R,
                    C_plasma=C_plasma, C_eff=C_eff, E_drug=E_drug,
                    resistance_fraction=base_ratio, TR=TR, TG=TR * (S + R),
                    total_cells=S + R)

    def run(self):
        cfg, c = self.cfg, self.c
        y = np.array([cfg.S0, cfg.R0, cfg.I0, c.f_R0, 0.0], dtype=float)
        if not np.all(np.isfinite(y)):
            raise ValueError("Initial condition is invalid")
        history = [self._snapshot(0, y)]
        # Solve separately for each day, avoiding LSODA crossing dose discontinuities.
        for day in range(1, cfg.T_days + 1):
            solution = solve_ivp(
                lambda t, state: self._system(t, state, day),
                (day - 1.0, float(day)), y, method="LSODA",
                rtol=1e-7, atol=1e-9, max_step=0.1,
            )
            if not solution.success:
                raise RuntimeError(f"Integration failed on day {day}: {solution.message}")
            y = solution.y[:, -1]
            if not np.all(np.isfinite(y)):
                raise RuntimeError("Non-finite values were produced by the simulator")
            y[:2] = np.maximum(y[:2], 0)
            y[2] = np.clip(y[2], 0, c.I_max)
            y[3] = np.clip(y[3], 0, 1)
            y[4] = max(y[4], 0)
            history.append(self._snapshot(day, y))
        return {"history": history}
