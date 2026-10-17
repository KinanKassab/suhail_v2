"""Strict request validation for research scenarios."""
from typing import List, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator


class SimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    patient_name: str = Field(default="حالة بحثية", min_length=1, max_length=100)
    patient_id: str = Field(default="-", max_length=50)
    notes: str = Field(default="", max_length=2000)
    S0: float = Field(default=5000, ge=0, le=1e12)
    R0: float = Field(default=100, ge=0, le=1e12)
    I0: float = Field(default=0.5, ge=0, le=1)
    G_S: float = Field(default=0.05, ge=0, le=1)
    G_R: float = Field(default=0.03, ge=0, le=1)
    T: float = Field(default=0.01, ge=0, le=1)
    I_s: float = Field(default=0.3, ge=0, le=1)
    I_r: float = Field(default=0.2, ge=0, le=1)
    C_G_I: float = Field(default=0.4, ge=0, le=1)
    N_G_I: float = Field(default=0.3, ge=0, le=1)
    sigma_C: float = Field(default=0.5, ge=0, le=1)
    sigma_L: float = Field(default=0.5, ge=0, le=1)
    sigma_I: float = Field(default=0.5, ge=0, le=1)
    SRF: float = Field(default=0.5, ge=0, le=1)
    sigma_A: float = Field(default=0.25, ge=0, le=1)
    calibration_mode: Literal["manual", "derived"] = "manual"
    dose_days: List[int] = Field(default_factory=lambda: [1, 8, 15, 22], min_length=1, max_length=365)
    dose_amount: float = Field(default=0.04, gt=0, le=10)
    T_days: int = Field(default=30, ge=1, le=365)
    K_cells: float = Field(default=1e9, gt=0, le=1e15)
    psa_actual: float = Field(default=0.5, ge=0)
    psa_expected: float = Field(default=0.7, ge=0)
    protein: float = Field(default=1, ge=0)
    sugar: float = Field(default=1, ge=0)
    sleep_h: float = Field(default=8, ge=0, le=24)
    activity_min: float = Field(default=30, ge=0, le=300)
    cd8: float = Field(default=1, ge=0)
    cd4: float = Field(default=1, ge=0)
    nk: float = Field(default=1, ge=0)
    ref_cd8: float = Field(default=1, gt=0)
    ref_cd4: float = Field(default=1, gt=0)
    ref_nk: float = Field(default=1, gt=0)
    R1: float = Field(default=200, ge=0)
    gleason: int = Field(default=7, ge=6, le=10)

    @field_validator("dose_days")
    @classmethod
    def normalize_doses(cls, value):
        if any(isinstance(d, bool) or not isinstance(d, int) for d in value):
            raise ValueError("أيام الجرعات يجب أن تكون أعداداً صحيحة")
        return sorted(set(value))

    @model_validator(mode="after")
    def check_combined(self):
        if any(d < 1 or d > self.T_days for d in self.dose_days):
            raise ValueError("كل يوم جرعة يجب أن يكون بين 1 ومدة المحاكاة")
        if self.S0 + self.R0 <= 0:
            raise ValueError("يلزم عدد أولي موجب من الخلايا")
        if self.calibration_mode == "derived" and self.psa_expected <= 0:
            raise ValueError("PSA المتوقع يجب أن يكون أكبر من الصفر")
        if self.calibration_mode == "derived" and self.R0 <= 0:
            raise ValueError("لا يمكن اشتقاق عامل المقاومة عند R0 = 0")
        if self.calibration_mode == "derived" and self.protein + self.sugar <= 0:
            raise ValueError("القيم الغذائية اللازمة للاشتقاق غير متوفرة")
        return self
