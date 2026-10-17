"""Research-only numerical calibration; not clinically validated."""
from dataclasses import dataclass, asdict
import math


def bounded(value: float, label: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label}: يجب إدخال عدد منتهٍ")
    return max(0.0, min(1.0, value))


@dataclass
class SuhailCalibration:
    sigma_C: float = 0.5
    sigma_L: float = 0.5
    sigma_I: float = 0.5
    SRF: float = 0.5
    sigma_A: float = 0.25

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} يجب أن يكون بين 0 و1")

    def to_dict(self) -> dict:
        return asdict(self)


def compute_sigma_C(psa_actual_drop: float, psa_expected_drop: float) -> float:
    """Exploratory ratio of *drops*, not raw PSA measurements or proven drug efficacy."""
    if psa_expected_drop <= 0:
        raise ValueError("الانخفاض المتوقع لـ PSA يجب أن يكون موجباً")
    return bounded(psa_actual_drop / psa_expected_drop, "sigma_C")


def compute_sigma_L(protein: float, sugar: float, sleep_h: float,
                    activity_min: float) -> float:
    """Unvalidated lifestyle proxy; protein/sugar must share compatible units."""
    if protein + sugar <= 0:
        raise ValueError("يجب إدخال قيمة غذائية موجبة واحدة على الأقل")
    return bounded((protein / (protein + sugar)) *
                   min(sleep_h / 8.0, 1.5) *
                   min(activity_min / 30.0, 1.5), "sigma_L")


def compute_sigma_I(cd8: float, cd4: float, nk: float,
                    ref_cd8: float = 1.0, ref_cd4: float = 1.0,
                    ref_nk: float = 1.0) -> float:
    reference = ref_cd8 + ref_cd4 + ref_nk
    if reference <= 0:
        raise ValueError("المقادير المناعية المرجعية يجب أن تكون موجبة")
    return bounded((cd8 + cd4 + nk) / reference, "sigma_I")


def compute_SRF(R0: float, R1: float) -> float:
    if R0 <= 0:
        raise ValueError("لا يمكن اشتقاق SRF عندما R0 = 0؛ أدخله يدوياً")
    return bounded((R1 - R0) / R0, "SRF")


def compute_sigma_A(gleason: int) -> float:
    return bounded((gleason - 6) / 4.0, "sigma_A")
