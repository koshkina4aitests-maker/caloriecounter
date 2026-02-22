from app.services import cardio_kcal, epley_1rm, kcal_from_macros


def test_kcal_from_macros_rounding() -> None:
    assert kcal_from_macros(protein_g=10, fat_g=10, carbs_g=10) == 10 * 4 + 10 * 9 + 10 * 4
    assert kcal_from_macros(protein_g=0, fat_g=0, carbs_g=0) == 0


def test_epley_1rm() -> None:
    assert epley_1rm(weight_kg=100, reps=1) == 100.0
    assert round(epley_1rm(weight_kg=100, reps=10), 2) == 133.33


def test_cardio_kcal() -> None:
    # MET 3.0, 60kg, 60 min -> 3 * 3.5 * 60 / 200 * 60 = 189
    assert cardio_kcal(met=3.0, duration_min=60, body_weight_kg=60) == 189

