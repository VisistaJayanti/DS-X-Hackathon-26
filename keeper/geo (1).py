"""Country and nationality normalization: names, demonyms and ISO codes -> ISO 3166-1 alpha-2."""
import re

# code: (country name, demonym, extra aliases)
COUNTRIES = {
    "US": ("United States", "American", ["usa", "u.s.", "u.s.a.", "united states of america", "america"]),
    "CA": ("Canada", "Canadian", []),
    "MX": ("Mexico", "Mexican", ["méxico", "mexicano", "mexicana"]),
    "BR": ("Brazil", "Brazilian", ["brasil", "brasileiro", "brasileira"]),
    "AR": ("Argentina", "Argentine", ["argentinian"]),
    "CO": ("Colombia", "Colombian", ["colombiano", "colombiana"]),
    "DO": ("Dominican Republic", "Dominican", ["dominicano", "dominicana", "república dominicana"]),
    "HT": ("Haiti", "Haitian", ["haïti", "ayiti"]),
    "PR": ("Puerto Rico", "Puerto Rican", []),
    "GT": ("Guatemala", "Guatemalan", []),
    "SV": ("El Salvador", "Salvadoran", ["salvadorean"]),
    "VE": ("Venezuela", "Venezuelan", []),
    "PE": ("Peru", "Peruvian", ["perú"]),
    "GB": ("United Kingdom", "British", ["uk", "u.k.", "england", "great britain", "english", "scottish", "welsh"]),
    "IE": ("Ireland", "Irish", []),
    "FR": ("France", "French", ["française", "français"]),
    "DE": ("Germany", "German", ["deutschland"]),
    "ES": ("Spain", "Spanish", ["españa", "español", "española"]),
    "PT": ("Portugal", "Portuguese", ["português", "portuguesa"]),
    "IT": ("Italy", "Italian", ["italia"]),
    "NL": ("Netherlands", "Dutch", ["holland"]),
    "CH": ("Switzerland", "Swiss", []),
    "SE": ("Sweden", "Swedish", []),
    "PL": ("Poland", "Polish", []),
    "UA": ("Ukraine", "Ukrainian", []),
    "RU": ("Russia", "Russian", []),
    "TR": ("Turkey", "Turkish", ["türkiye"]),
    "AE": ("United Arab Emirates", "Emirati", ["uae", "dubai"]),
    "SA": ("Saudi Arabia", "Saudi", []),
    "IL": ("Israel", "Israeli", []),
    "EG": ("Egypt", "Egyptian", []),
    "NG": ("Nigeria", "Nigerian", []),
    "KE": ("Kenya", "Kenyan", []),
    "ZA": ("South Africa", "South African", []),
    "ET": ("Ethiopia", "Ethiopian", []),
    "IN": ("India", "Indian", ["bharat"]),
    "PK": ("Pakistan", "Pakistani", []),
    "BD": ("Bangladesh", "Bangladeshi", []),
    "CN": ("China", "Chinese", ["prc", "people's republic of china"]),
    "HK": ("Hong Kong", "Hong Konger", []),
    "TW": ("Taiwan", "Taiwanese", []),
    "JP": ("Japan", "Japanese", []),
    "KR": ("South Korea", "Korean", ["korea", "republic of korea"]),
    "VN": ("Vietnam", "Vietnamese", ["viet nam"]),
    "PH": ("Philippines", "Filipino", ["filipina"]),
    "TH": ("Thailand", "Thai", []),
    "SG": ("Singapore", "Singaporean", []),
    "MY": ("Malaysia", "Malaysian", []),
    "ID": ("Indonesia", "Indonesian", []),
    "AU": ("Australia", "Australian", []),
    "NZ": ("New Zealand", "New Zealander", ["kiwi"]),
}

_LOOKUP = {}
for code, (name, demonym, aliases) in COUNTRIES.items():
    for k in [code, name, demonym, *aliases]:
        _LOOKUP[k.lower()] = code


def to_code(value):
    """'India' / 'Indian' / 'in' / 'IN' -> 'IN'. Unknown values return None."""
    if not value:
        return None
    v = re.sub(r"\s+", " ", str(value)).strip().lower().rstrip(".")
    return _LOOKUP.get(v)


def name(code):
    return COUNTRIES.get(code, (code,))[0] if code else ""


def options():
    return [{"code": c, "name": v[0]} for c, v in sorted(COUNTRIES.items(), key=lambda kv: kv[1][0])]
