def fmt_moeda(valor) -> str:
    texto = format(float(valor), ",.2f").replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_percentual(valor) -> str:
    texto = format(float(valor), ".2f").replace(".", ",")
    return f"{texto}%"
