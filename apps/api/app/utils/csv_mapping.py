"""
Mapping des colonnes CSV prospects → champs des modèles Contact et Company.

Colonnes identifiées dans les fichiers sources :
    row_num, prospect_first_name, prospect_last_name, prospect_full_name,
    prospect_job_title, contact_professions_email, prospect_linkedin,
    prospect_professional_email_hashed, prospect_job_level_main,
    prospect_job_level_array, prospect_job_seniority_level,
    prospect_job_department_main, prospect_job_department_array,
    prospect_job_department, prospect_country_name, prospect_region_name,
    prospect_city, prospect_experience, prospect_skills, prospect_interests,
    prospect_company_name, prospect_company_website, prospect_company_linkedin,
    contact_professional_email_status, contact_emails, contact_mobile_phone,
    contact_phone_numbers, created_at, prospect_linkedin_url_array,
    business_id, prospect_id, sexe/sex/gender (optionnel)
"""

# ── Contact : colonne CSV → champ modèle ─────────────────────────────────────
CONTACT_COLUMN_MAP: dict[str, str] = {
    "prospect_first_name":              "first_name",
    "prospect_last_name":               "last_name",
    "sexe":                             "sex",
    "sex":                              "sex",
    "gender":                           "sex",
    "prospect_gender":                  "sex",
    "contact_gender":                   "sex",
    "prospect_job_title":               "job_title",
    "prospect_job_level_main":          "job_level",
    "prospect_linkedin":                "linkedin_url",
    "prospect_country_name":            "country",
    "prospect_region_name":             "region",
    "prospect_city":                    "city",
    "contact_professions_email":        "email",
    "contact_professional_email_status": "email_status",
    "contact_mobile_phone":             "phone",
    "prospect_id":                      "source_prospect_id",
    "business_id":                      "source_business_id",
}

# ── Company : colonne CSV → champ modèle ─────────────────────────────────────
COMPANY_COLUMN_MAP: dict[str, str] = {
    "prospect_company_name":     "name",
    "prospect_company_website":  "website",
    "prospect_company_linkedin": "linkedin_url",
    "prospect_country_name":     "country",
    "business_id":               "source_business_id",
}

# ── Colonnes ignorées ─────────────────────────────────────────────────────────
IGNORED_COLUMNS: frozenset[str] = frozenset({
    "row_num",
    "prospect_full_name",                 # redondant avec first/last name séparés
    "prospect_professional_email_hashed", # hash de l'email, inutile
    "prospect_job_level_array",           # redondant avec job_level_main
    "prospect_job_seniority_level",       # redondant avec job_level_main
    "prospect_job_department_main",       # non utilisé pour l'instant
    "prospect_job_department_array",      # non utilisé pour l'instant
    "prospect_job_department",            # non utilisé pour l'instant
    "prospect_experience",                # JSON complexe, non utilisé pour l'instant
    "prospect_skills",                    # JSON complexe, non utilisé pour l'instant
    "prospect_interests",                 # JSON complexe, non utilisé pour l'instant
    "contact_emails",                     # redondant avec contact_professions_email
    "contact_phone_numbers",              # redondant avec contact_mobile_phone
    "created_at",                         # date dans la source, pas notre BDD
    "prospect_linkedin_url_array",        # redondant avec prospect_linkedin
})


def split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    """Sépare 'Prénom Nom' en (first_name, last_name).

    Utilisé en fallback si prospect_first_name / prospect_last_name sont absents.
    Règle : premier mot = prénom, le reste = nom de famille.
    """
    if not full_name or not full_name.strip():
        return None, None
    parts = full_name.strip().split(" ", maxsplit=1)
    first = parts[0] or None
    last = (parts[1] if len(parts) > 1 else None) or None
    return first, last
