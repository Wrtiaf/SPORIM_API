"""Расчёт выплат в целых виртуальных баллах."""

from decimal import ROUND_HALF_UP, Decimal

# Коэффициенты хранятся как float, поэтому переводим их в Decimal через строку,
# чтобы избежать двоичных артефактов вида 22.499999999.
PAYOUT_QUANTUM = Decimal("1")


def calculate_payout(amount: int, coefficient: float) -> int:
    """Вычисляет выплату по ставке в целых баллах.

    Правило: `amount * coefficient` округляется до целого по правилу
    «половина вверх» (ROUND_HALF_UP). Например, 15 * 1.5 = 22.5 -> 23.

    Args:
        amount: размер ставки в баллах (>= 0).
        coefficient: зафиксированный коэффициент.

    Returns:
        Целая сумма выплаты в баллах.
    """
    if amount <= 0:
        return 0
    value = Decimal(amount) * Decimal(str(coefficient))
    return int(value.quantize(PAYOUT_QUANTUM, rounding=ROUND_HALF_UP))
