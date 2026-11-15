"""Fixture module 35."""

VALUE = 35


def compute(n):
    total = 0
    for k in range(n):
        total = (total * 31 + k + VALUE) % 1000003
    return total
