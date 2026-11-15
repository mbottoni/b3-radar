"""Short sector groups from CVM's activity sector (SETOR_ATIV).

CVM's label splits one business across several labels: a holding company
gets "Emp. Adm. Part. - " in front of its subsidiaries' sector, sometimes
abbreviated ("Emp. Adm. Part. - Const. Civil, Mat. Const. e Decoração" for
JHSF next to "Construção Civil, Mat. Constr. e Decoração" for Cyrela), and
neighbouring activities get their own label (power and water utilities).
``group`` folds them into about fifteen groups, for reading and for
counting how concentrated a list is. It is display only: eligibility (the
financial-sector exclusion) still reads CVM's own label, and the groups are
not part of the scoring rules.

The mapping is by keyword in the label once the holding prefix is removed
and accents are stripped, so CVM's spelling variants (``Máqs., Equip.``,
``Serviços médicos``) land in the same group. METHODOLOGY.md lists it.
"""

from __future__ import annotations

import re
import unicodedata

OTHER = "Other"
# (group, keywords in CVM's label): first match wins. Financials first, so
# "Crédito Imobiliário" is not read as real estate.
GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Financials", ("banco", "intermediacao financeira", "seguradora", "arrendamento mercantil", "securitizacao",
                    "credito imobiliario", "bolsas de valores", "factoring")),
    ("Real estate", ("construcao civil", "const. civil")),
    ("Retail", ("comercio",)),
    ("Apparel", ("textil",)),
    ("Utilities", ("energia eletrica", "saneamento")),
    ("Oil & gas", ("petroleo",)),
    ("Mining & steel", ("extracao mineral", "metalurgia")),
    ("Paper & chemicals", ("papel", "petroquimico", "embalage", "reflorestamento")),
    ("Industrials", ("maquinas", "maqs.", "atividades industriais")),
    ("Transport", ("transporte",)),
    ("Food & agri", ("alimentos", "agricultura", "bebidas", "pesca")),
    ("Health", ("servicos medicos", "farmaceutico")),
    ("Education", ("educacao",)),
    ("Tech & media", ("informatica", "graficas")),
    ("Telecom", ("telecomunicac",)),
    ("Leisure & travel", ("hospedagem", "lazer")),
)
NAMES = tuple(g for g, _ in GROUPS) + (OTHER,)
_HOLDING = re.compile(r"^emp\.?\s*adm\.?\s*part(icipacoes|\.)?\s*-?\s*")


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def base(label: str) -> str:
    """CVM's label without the holding-company prefix, accents or case."""
    return _HOLDING.sub("", _plain(label or ""))


def group(label: str) -> str:
    """The short group of a CVM activity-sector label (``OTHER`` if none:
    holdings with no main sector, "Serviços Diversos", a blank label)."""
    b = base(label)
    for name, keys in GROUPS:
        if any(k in b for k in keys):
            return name
    return OTHER
