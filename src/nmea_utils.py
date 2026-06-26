import functools


def checksum(sentence: str) -> str:
    return format(functools.reduce(lambda a, b: a ^ b, (ord(c) for c in sentence)), "02X")


def build_sentence(body: str) -> str:
    return f"${body}*{checksum(body)}\r\n"


def build_mwv(awa_deg: float, aws_kts: float) -> str:
    """Phrase MWV vent apparent — envoyée au TP22 en mode Conservateur d'Allure."""
    awa_deg = round(awa_deg % 360, 1)
    aws_kts = round(max(0.0, aws_kts), 1)
    return build_sentence(f"WIMWV,{awa_deg:.1f},R,{aws_kts:.1f},N,A")
