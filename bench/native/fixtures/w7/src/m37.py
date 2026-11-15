"""Fixture module 37."""

VALUE = 37


def compute(n):
    total = 0
    for k in range(n):
        total = (total * 31 + k + VALUE) % 1000003
    return total
