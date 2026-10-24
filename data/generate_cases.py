"""Generate the synthetic Coverage Keeper evaluation set.

ALL DATA IS SYNTHETIC. Names, employers, clinicians and IDs are invented.

Usage: python data/generate_cases.py   -> writes data/cases/*.json
Each case: member basics, documents (plain text, some messy / non-English), and ground-truth labels:
  correct_pathways   : pathway IDs any of which is an acceptable top-1 answer ("NONE" = no pathway)
  evidence_sufficient: whether the documents already prove the best pathway
  gaps               : gap codes the tool should raise (see keeper/gaps.py GAP_CODES)
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "cases"
LOOKBACK = ["2026-07", "2026-08", "2026-09"]
CASES = []


def case(cid, title, member, docs, correct, sufficient, gaps, notes=""):
    m = {"lookback_months": LOOKBACK, "notice_type": "Request for Information (RFI)", **member}
    CASES.append({
        "case_id": cid, "title": title, "member": m,
        "documents": [{"doc_id": f"D{i + 1}", "filename": fn, "text": t.strip("\n")} for i, (fn, t) in enumerate(docs)],
        "labels": {"correct_pathways": correct, "evidence_sufficient": sufficient, "gaps": sorted(gaps), "notes": notes},
    })


def paystubs(employer, name, rate, periods, ocr=False):
    out = []
    for start, end, hrs in periods:
        gross = round(rate * hrs, 2)
        h = "Hcurs" if ocr else "Hours"
        out.append(f"""{employer.upper()}
EARNINGS STATEMENT
Employee: {name}
Pay period: {start} - {end}
Pay date: {end}
Rate: ${rate:.2f}/hr
Regular {h} worked: {hrs}
Gross pay: ${gross:,.2f}
Net pay: ${gross * 0.88:,.2f}
YTD gross: ${gross * 14:,.2f}""")
    return "\n\n- - - - - - - - - - - - - - -\n\n".join(out)


def clinic_letter(clinic, clinician, creds, date, name, dob, body):
    return f"""{clinic}
{date}

To Whom It May Concern:

RE: {name}   DOB: {dob}

{body}

Sincerely,
{clinician}, {creds}
{clinic}"""


# ---------------------------------------------------------------- medical frailty
case("C01", "Medical frailty: letter names diagnoses but not work impact (DEMO)",
     {"name": "Rosa M. (synthetic)", "age": 41, "language": "es", "household": "Lives alone", "notice_received_date": "2026-10-13"},
     [("dr_letter_alvarez.txt", clinic_letter(
         "Harborview Community Health Center", "Dr. Elena Alvarez", "MD", "October 2, 2026", "Rosa M.", "03/14/1985",
         """Ms. M. has been my patient since 2021. She has chronic obstructive pulmonary disease (COPD, GOLD stage 3)
and congestive heart failure with reduced ejection fraction (EF 30%).
She uses home oxygen at night and is seen in clinic every 4 weeks for monitoring.
Her medications include tiotropium, furosemide and carvedilol.
Please contact our office with any questions.""")),
      ("paystub_sept.txt", paystubs("Bright Clean Services LLC", "Rosa M.", 15.50,
                                     [("09/01/2026", "09/15/2026", 14.0), ("09/16/2026", "09/30/2026", 12.0)]))],
     ["EX_MEDICALLY_FRAIL"], False, ["FRAILTY_NO_WORK_IMPACT"],
     "Diagnosis is serious/complex but the letter never says it impairs ability to work. 26 hrs / $403 in Sept: work and income not met.")

case("C02", "Medical frailty: letter explicitly states condition prevents work",
     {"name": "Daniel K. (synthetic)", "age": 52, "language": "en", "household": "Lives with spouse", "notice_received_date": "2026-10-06"},
     [("letter_pulm.txt", clinic_letter(
         "North Shore Pulmonary Associates", "Dr. Priya Raman", "MD", "September 28, 2026", "Daniel K.", "07/22/1974",
         """Mr. K. has idiopathic pulmonary fibrosis diagnosed in 2023 and is on continuous supplemental oxygen.
Due to this condition he is unable to work or participate in job training or volunteer activities.
His condition significantly impairs his ability to meet any work requirement, and I expect this to continue for at least 12 months."""))],
     ["EX_MEDICALLY_FRAIL"], True, [])

case("C03", "Behavioral health frailty: psychiatrist letter states inability to work",
     {"name": "Tasha W. (synthetic)", "age": 29, "language": "en", "household": "Lives with roommate", "notice_received_date": "2026-10-15"},
     [("psych_letter.txt", clinic_letter(
         "Riverside Behavioral Health", "Marcus Lee", "PMHNP-BC", "10/08/2026", "Tasha W.", "1997-05-02",
         """I am writing at the request of my patient, Ms. W., who is in treatment for major depressive disorder, recurrent, severe,
and post-traumatic stress disorder. She had a psychiatric hospitalization in June 2026 and attends weekly therapy.
In my clinical opinion her symptoms currently prevent her from maintaining employment or a regular schedule of 80 hours per month."""))],
     ["EX_MEDICALLY_FRAIL"], True, [])

case("C04", "SUD frailty + treatment program (opioid use disorder, early recovery)",
     {"name": "Kevin O. (synthetic)", "age": 36, "language": "en", "household": "Sober house", "notice_received_date": "2026-10-01"},
     [("otp_letter.txt", """BAYSIDE RECOVERY SERVICES - OPIOID TREATMENT PROGRAM
Date: 9/30/2026
Patient: Kevin O.

This letter confirms that the above patient has been enrolled in our opioid treatment program since 02/10/2026
and is currently receiving daily methadone dosing and weekly counseling.
Diagnosis: Opioid use disorder, severe, in early remission (8 months).

Program coordinator: Janelle Ortiz, LADC I"""),
      ("pcp_letter.txt", clinic_letter("Bayside Primary Care", "Dr. Samuel Greene", "DO", "October 3, 2026", "Kevin O.", "11/30/1989",
                                       """Mr. O. is my patient and is in active treatment for opioid use disorder.
His daily treatment schedule and early recovery significantly limit his ability to work at this time;
attempting 80 hours of work per month would put his recovery at serious risk."""))],
     ["EX_MEDICALLY_FRAIL", "EX_SUD_TREATMENT"], True, [])

case("C05", "SUD in stable recovery (6 yrs) - not frail, but works 90+ hours",
     {"name": "Brian T. (synthetic)", "age": 47, "language": "en", "household": "Lives with partner", "notice_received_date": "2026-10-09"},
     [("pcp_note.txt", clinic_letter("Mill City Family Medicine", "Dr. Ann Kowalski", "MD", "October 1, 2026", "Brian T.", "02/11/1979",
                                     """Mr. T. has a history of alcohol use disorder and has been in sustained remission since 2020 (over 6 years).
He is doing well and is currently employed full time.""")),
      ("stubs.txt", paystubs("Merrimack Valley Auto Parts", "Brian T.", 18.25,
                             [("08/31/2026", "09/13/2026", 46.0), ("09/14/2026", "09/27/2026", 47.5)]))],
     ["WORK_80", "INCOME_580"], True, [],
     "Stable recovery (5+ yrs) is excluded from SUD frailty; work pathway applies.")

case("C06", "Behavioral health frailty: vague letter ('may have difficulty')",
     {"name": "Jordan P. (synthetic)", "age": 33, "language": "en", "household": "Lives with parents", "notice_received_date": "2026-10-17"},
     [("bh_letter.txt", clinic_letter("Pioneer Valley Counseling", "Renee Dubois", "LICSW", "October 12, 2026", "Jordan P.", "08/19/1993",
                                      """Jordan has been in counseling with me since January 2025 for bipolar I disorder.
Jordan is engaged in treatment and takes medication as prescribed.
At times Jordan may have difficulty with stressful environments."""))],
     ["EX_MEDICALLY_FRAIL"], False, ["FRAILTY_NO_WORK_IMPACT"])

case("C07", "Alcohol use disorder: diagnosis only, no program, no impact statement",
     {"name": "Luis F. (synthetic)", "age": 44, "language": "es", "household": "Lives alone", "notice_received_date": "2026-10-20"},
     [("pcp_aud.txt", clinic_letter("Lawrence Family Health", "Dr. Carmen Ruiz", "MD", "10/14/2026", "Luis F.", "06/06/1982",
                                    """Mr. F. was seen today. He meets criteria for alcohol use disorder, moderate.
He would benefit from a referral to outpatient treatment, which we discussed.
He also has hypertension, which is controlled."""))],
     ["EX_MEDICALLY_FRAIL"], False, ["FRAILTY_NO_WORK_IMPACT"])

case("C08", "Spanish-language clinician letter stating inability to work",
     {"name": "Ana G. (synthetic)", "age": 58, "language": "es", "household": "Lives with daughter", "notice_received_date": "2026-10-02"},
     [("carta_medica.txt", """Centro de Salud Comunitario Esperanza
Boston, 5 de octubre de 2026

A quien corresponda:

Paciente: Ana G.   Fecha de nacimiento: 12/01/1968

La Sra. G. tiene artritis reumatoide severa con daño articular en ambas manos y rodillas,
y recibe tratamiento con infusiones mensuales.
Su condición le impide trabajar y limita gravemente sus actividades de la vida diaria.

Atentamente,
Dra. Lucía Fernández, MD""")],
     ["EX_MEDICALLY_FRAIL"], True, ["DOC_TRANSLATION"])

case("C09", "Chinese-speaking member: oncology letter, on chemotherapy, cannot work",
     {"name": "Wei L. (synthetic)", "age": 61, "language": "zh", "household": "Lives with spouse", "notice_received_date": "2026-10-10"},
     [("onc_letter.txt", clinic_letter("Chinatown Community Oncology Clinic", "Dr. Helen Zhou", "MD", "October 7, 2026", "Wei L.", "04/18/1965",
                                       """Mr. L. is receiving chemotherapy every two weeks for stage III colon cancer.
Treatment side effects include severe fatigue and neuropathy.
He is not able to work during treatment, which is expected to continue through at least March 2027."""))],
     ["EX_MEDICALLY_FRAIL"], True, [])

# ---------------------------------------------------------------- caregiving
case("C10", "Parent of a 13-year-old (exempt)",
     {"name": "Keisha R. (synthetic)", "age": 38, "language": "en", "household": "Self + son (13)", "notice_received_date": "2026-10-05"},
     [("birth_cert.txt", """COMMONWEALTH OF MASSACHUSETTS
CERTIFIED COPY OF BIRTH RECORD
Child's name: Malik R.
Date of birth: 02/03/2013
Mother: Keisha R.
Place of birth: Brockton, MA"""),
      ("attest.txt", """Caregiver statement
I, Keisha R., live with my son Malik R. and I am his primary caregiver.
Signed: Keisha R.   Date: 10/07/2026""")],
     ["EX_CAREGIVER_CHILD"], True, [], "Child born 2013-02-03 is 13 as of Oct 2026.")

case("C11", "Parent of a 14-year-old (NOT exempt) with part-time low-hour job",
     {"name": "Paulo S. (synthetic)", "age": 45, "language": "pt", "household": "Self + daughter (14)", "notice_received_date": "2026-10-08"},
     [("birth_cert.txt", """COMMONWEALTH OF MASSACHUSETTS
BIRTH RECORD
Child's name: Bianca S.
Date of birth: 06/21/2012
Father: Paulo S."""),
      ("paystub.txt", paystubs("Framingham Bakery Co", "Paulo S.", 7.00,
                                [("09/01/2026", "09/30/2026", 30.0)]))],
     ["NONE"], False, ["NO_QUALIFYING_PATHWAY", "HOURS_SHORT", "INCOME_SHORT"],
     "Child is 14 (born June 2012). 30 hrs at a $7.00 tipped base wage = $210.")

case("C12", "Claims caregiving for a young child but no proof of child's age",
     {"name": "Marie-Claude J. (synthetic)", "age": 31, "language": "ht", "household": "Self + child", "notice_received_date": "2026-10-12"},
     [("attest.txt", """CAREGIVER ATTESTATION
I take care of my child every day. My child lives with me.
I am the only person who takes care of my child.
Name: Marie-Claude J.
Date: October 9, 2026""")],
     ["EX_CAREGIVER_CHILD"], False, ["CHILD_AGE_PROOF"])

case("C13", "Lives with and cares for disabled mother (attestation + mother's SSDI letter)",
     {"name": "Hoa N. (synthetic)", "age": 50, "language": "vi", "household": "Self + mother (78)", "notice_received_date": "2026-10-03"},
     [("attest.txt", """CAREGIVER STATEMENT
I, Hoa N., live with my mother, Lan N. I help her every day with bathing, dressing, meals and medications.
I provide about 6 hours of care each day.
Signature: Hoa N.   Date: 09/29/2026"""),
      ("ssa_mother.txt", """SOCIAL SECURITY ADMINISTRATION
Notice of Award
Beneficiary: Lan N.
We found that you became disabled under our rules on March 4, 2019.
You are entitled to monthly disability benefits beginning September 2019.""")],
     ["EX_CAREGIVER_DISABLED"], True, [])

case("C14", "Caregiver attestation but no evidence the person cared for has a disability",
     {"name": "Gary B. (synthetic)", "age": 55, "language": "en", "household": "Self + brother", "notice_received_date": "2026-10-16"},
     [("attest.txt", """Statement of care
My name is Gary B. I live with my brother Steve and take care of him most days.
I drive him to appointments and help with cooking and cleaning.
Gary B., 10/10/2026""")],
     ["EX_CAREGIVER_DISABLED"], False, ["CAREGIVER_DISABILITY_PROOF"])

case("C15", "Works 90 hrs AND parent of a 5-year-old (two valid pathways)",
     {"name": "Fatima A. (synthetic)", "age": 27, "language": "en", "household": "Self + daughter (5)", "notice_received_date": "2026-10-11"},
     [("stubs.txt", paystubs("Quincy Market Grocers", "Fatima A.", 16.00,
                             [("09/01/2026", "09/14/2026", 44.0), ("09/15/2026", "09/28/2026", 46.0)])),
      ("birth.txt", """BIRTH CERTIFICATE (copy)
Name of child: Amira A.
Date of Birth: May 9, 2021
Mother: Fatima A.""")],
     ["EX_CAREGIVER_CHILD", "WORK_80", "INCOME_580"], True, [])

# ---------------------------------------------------------------- pregnancy / postpartum
case("C16", "Postpartum, delivered 7 months ago",
     {"name": "Jasmine T. (synthetic)", "age": 24, "language": "en", "household": "Self + infant", "notice_received_date": "2026-10-07"},
     [("discharge.txt", """BOSTON WOMEN'S HOSPITAL - DISCHARGE SUMMARY
Patient: Jasmine T.
Admission date: 03/14/2026
Date of delivery: 03/15/2026
Delivery: spontaneous vaginal delivery, healthy female infant
Discharge date: 03/17/2026""")],
     ["EX_PREGNANT_POSTPARTUM", "EX_CAREGIVER_CHILD"], True, [])

case("C17", "Postpartum near the 12-month boundary",
     {"name": "Camila V. (synthetic)", "age": 30, "language": "es", "household": "Self + infant", "notice_received_date": "2026-10-14"},
     [("discharge.txt", """MERCY MEDICAL CENTER SPRINGFIELD
Discharge Summary - Obstetrics
Patient name: Camila V.
Delivered: 11/10/2025 (cesarean section)
Infant: male, 7 lb 2 oz""")],
     ["EX_PREGNANT_POSTPARTUM", "EX_CAREGIVER_CHILD"], True, ["POSTPARTUM_ENDING"],
     "Delivery 2025-11-10: postpartum placeholder window ends 2026-11-10, within 30 days of today.")

case("C18", "Postpartum window over (delivered 13+ months ago, no child proof) but works 85 hrs",
     {"name": "Brianna H. (synthetic)", "age": 26, "language": "en", "household": "Lives with partner", "notice_received_date": "2026-10-04"},
     [("discharge.txt", """ST. LUKE'S HOSPITAL NEW BEDFORD
Patient: Brianna H.
Date of delivery: 2025-09-01
Outcome: stillbirth at 36 weeks. Bereavement services offered."""),
      ("stubs.txt", paystubs("New Bedford Seafood Processing", "Brianna H.", 17.00,
                             [("09/01/2026", "09/15/2026", 41.0), ("09/16/2026", "09/30/2026", 44.0)]))],
     ["WORK_80", "INCOME_580"], True, [])

case("C19", "Currently pregnant (prenatal letter with due date)",
     {"name": "Nadia E. (synthetic)", "age": 22, "language": "en", "household": "Lives with mother", "notice_received_date": "2026-10-18"},
     [("prenatal.txt", clinic_letter("Codman Square Health Center - OB/GYN", "Sarah Kim", "CNM", "10/02/2026", "Nadia E.", "01/05/2004",
                                     """This letter confirms that Ms. E. is currently pregnant and receiving prenatal care at our health center.
Estimated due date: 03/22/2027."""))],
     ["EX_PREGNANT_POSTPARTUM"], True, [])

# ---------------------------------------------------------------- education / combination
case("C20", "75 hrs work + 3-credit class (combination meets 80)",
     {"name": "Andre L. (synthetic)", "age": 23, "language": "en", "household": "Lives with roommates", "notice_received_date": "2026-10-09"},
     [("volunteer_log.txt", """GREATER BOSTON FOOD BANK - VOLUNTEER HOURS VERIFICATION
Volunteer: Andre L.
Month: September 2026
Total hours: 75
Supervisor: Dana Whitfield, Volunteer Manager (617-555-0142)"""),
      ("enrollment.txt", """BUNKER HILL COMMUNITY COLLEGE - OFFICE OF THE REGISTRAR
Enrollment Verification
Student: Andre L.
Term: Fall 2026 (09/02/2026 - 12/18/2026)
Credit hours: 3
Enrollment status: Less than half-time""")],
     ["COMBINATION"], True, [], "75 volunteer + 3 credits x 3 x 4.33 = 39 -> 114 hrs.")

case("C21", "75 hrs volunteering + school letter with no credits or status",
     {"name": "Sofia D. (synthetic)", "age": 21, "language": "pt", "household": "Lives with family", "notice_received_date": "2026-10-19"},
     [("volunteer.txt", """Cape Verdean Community Center
Volunteer hours - September 2026
Sofia D. ......... 75 hours
Coordinator: Paulo Andrade"""),
      ("school.txt", """ROXBURY COMMUNITY COLLEGE
To whom it may concern,
This is to confirm that Sofia D. is registered for courses this fall semester.
Registrar's Office""")],
     ["COMBINATION", "EDUCATION"], False, ["ENROLLMENT_STATUS_UNSTATED"])

case("C22", "Full-time university student",
     {"name": "Minh T. (synthetic)", "age": 20, "language": "vi", "household": "Lives in dorm", "notice_received_date": "2026-10-06"},
     [("enroll.txt", """UNIVERSITY OF MASSACHUSETTS LOWELL
ENROLLMENT VERIFICATION CERTIFICATE
Student: Minh T.
Term: Fall 2026, 09/03/2026 - 12/20/2026
Enrollment status: Full-time (15 credits)""")],
     ["EDUCATION"], True, [])

case("C23", "Letter says 'part-time' without half-time determination",
     {"name": "Grace O. (synthetic)", "age": 34, "language": "en", "household": "Self + spouse", "notice_received_date": "2026-10-13"},
     [("enroll.txt", """Quinsigamond Community College
Dear Student Services,
Grace O. is enrolled as a part-time student for the Fall 2026 term.
Registrar""")],
     ["EDUCATION"], False, ["ENROLLMENT_STATUS_UNSTATED"])

case("C24", "Half-time graduate student",
     {"name": "Omar Z. (synthetic)", "age": 28, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-01"},
     [("enroll.txt", """BOSTON UNIVERSITY - OFFICE OF THE UNIVERSITY REGISTRAR
Certification of Enrollment
Student: Omar Z.
Term: Fall 2026
Status: Half-time (6 credits, graduate)""")],
     ["EDUCATION"], True, [])

# ---------------------------------------------------------------- income / hours
case("C25", "Gig income just above $580 (irregular weekly payouts)",
     {"name": "Tyrone J. (synthetic)", "age": 39, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-10"},
     [("gig.txt", """DASHRIDE DRIVER EARNINGS SUMMARY
Driver: Tyrone J.
Week of 09/01/2026: $212.40
Week of 09/08/2026: $0.00
Week of 09/15/2026: $151.30
Week of 09/22/2026: $232.50
Week of 09/29/2026 (paid 10/03): $98.00""")],
     ["INCOME_580"], True, [], "Sept payouts (09/01-09/22) = $596.20; the week of 09/29 is paid in October.")

case("C26", "Gig income just below $580",
     {"name": "Kayla M. (synthetic)", "age": 25, "language": "en", "household": "Lives with sister", "notice_received_date": "2026-10-15"},
     [("gig.txt", """QuickCart Shopper - Monthly Statement
Shopper: Kayla M.
Statement month: September 2026
Total earnings (incl. tips): $571.40
Orders completed: 64""")],
     ["NONE"], False, ["NO_QUALIFYING_PATHWAY", "INCOME_SHORT"])

case("C27", "Earnings exactly $580.00",
     {"name": "Ibrahim S. (synthetic)", "age": 42, "language": "en", "household": "Lives with family", "notice_received_date": "2026-10-07"},
     [("stub.txt", paystubs("Lowell Laundromat", "Ibrahim S.", 14.50, [("09/01/2026", "09/30/2026", 40.0)]))],
     ["INCOME_580"], True, [])

case("C28", "Conflicting volunteer hours: log vs coordinator letter",
     {"name": "Ellen C. (synthetic)", "age": 60, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-12"},
     [("log.txt", """Worcester Senior Center - Volunteer Sign-In Totals
Volunteer: Ellen C.
September 2026 total: 72 hours"""),
      ("letter.txt", """Worcester Senior Center
October 1, 2026
To whom it may concern: Ellen C. volunteers with our meals program approximately 25 hours per week.
- Rita Moreau, Volunteer Coordinator""")],
     ["WORK_80"], False, ["DOC_CONFLICT"], "Log 72 hrs vs ~25/wk (108/mo).")

case("C29", "Pay stubs vs employer letter conflict on earnings",
     {"name": "Victor A. (synthetic)", "age": 37, "language": "es", "household": "Lives with partner", "notice_received_date": "2026-10-16"},
     [("stub.txt", paystubs("Chelsea Produce Distributors", "Victor A.", 15.00, [("09/01/2026", "09/30/2026", 36.0)])),
      ("employer.txt", """CHELSEA PRODUCE DISTRIBUTORS
10/02/2026
Victor A. is employed with us and works 20 hours per week at $15.00 per hour.
HR Department""")],
     ["INCOME_580", "WORK_80"], False, ["DOC_CONFLICT"], "Stub: 36 hrs/$540. Letter implies ~86.6 hrs / $1,299.")

case("C30", "Job training (MassHire) 60 hrs + volunteering 25 hrs",
     {"name": "Derek W. (synthetic)", "age": 49, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-05"},
     [("masshire.txt", """MASSHIRE BOSTON CAREER CENTER
WIOA Training Participation Record
Participant: Derek W.
Program: CDL Class B training
September 2026 attendance: 60 hours"""),
      ("vol.txt", """Habitat for Humanity Greater Boston - Volunteer Record
Derek W.
Sept 2026: 25 hours""")],
     ["WORK_80"], True, [])

case("C31", "Restaurant server, 82 hours on stubs (tipped wage)",
     {"name": "Jenny P. (synthetic)", "age": 32, "language": "en", "household": "Self + roommate", "notice_received_date": "2026-10-11"},
     [("stubs.txt", paystubs("Harbor Grille", "Jenny P.", 6.75,
                             [("08/31/2026", "09/13/2026", 40.0), ("09/14/2026", "09/27/2026", 42.0)], ocr=True))],
     ["WORK_80"], True, [], "Messy OCR ('Hcurs'). 82 hrs x $6.75 tipped base = $553.50, so income pathway is NOT met.")

case("C32", "Portuguese-language employer declaration, 96 hours",
     {"name": "Joana R. (synthetic)", "age": 35, "language": "pt", "household": "Lives with husband", "notice_received_date": "2026-10-08"},
     [("declaracao.txt", """LIMPEZA BRILHANTE LTDA - Framingham, MA
Declaração de Trabalho

Declaramos que Joana R. trabalha em nossa empresa como auxiliar de limpeza.
Em setembro de 2026, trabalhou um total de 96 horas.

Framingham, 2 de outubro de 2026
Carlos Mendes, Gerente""")],
     ["WORK_80"], True, ["DOC_TRANSLATION"])

case("C33", "Haitian Creole speaker, English pay stubs, 88 hours",
     {"name": "Jean-Baptiste P. (synthetic)", "age": 46, "language": "ht", "household": "Self + wife", "notice_received_date": "2026-10-02"},
     [("stubs.txt", paystubs("Mattapan Home Health", "Jean-Baptiste P.", 17.50,
                             [("09/01/2026", "09/15/2026", 44.0), ("09/16/2026", "09/30/2026", 44.0)]))],
     ["WORK_80", "INCOME_580"], True, [])

case("C34", "Pay stubs only from March 2026 (outside lookback)",
     {"name": "Robert N. (synthetic)", "age": 53, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-14"},
     [("old_stubs.txt", paystubs("Springfield Warehouse Inc", "Robert N.", 16.00,
                                 [("03/01/2026", "03/14/2026", 45.0), ("03/15/2026", "03/28/2026", 45.0)]))],
     ["WORK_80", "INCOME_580"], False, ["OUTSIDE_LOOKBACK"])

case("C35", "No qualifying pathway (10 hrs/month, no exemptions)",
     {"name": "Chris D. (synthetic)", "age": 30, "language": "en", "household": "Lives with friends", "notice_received_date": "2026-10-09"},
     [("stub.txt", paystubs("Corner Coffee Roasters", "Chris D.", 15.00, [("09/01/2026", "09/30/2026", 10.0)]))],
     ["NONE"], False, ["NO_QUALIFYING_PATHWAY", "HOURS_SHORT", "INCOME_SHORT"])

# ---------------------------------------------------------------- other exemptions & out of scope
case("C36", "Member is 65 (out of scope)",
     {"name": "Dolores F. (synthetic)", "age": 65, "language": "es", "household": "Lives alone", "notice_received_date": "2026-10-06"},
     [("id.txt", """MASSACHUSETTS IDENTIFICATION CARD
Name: Dolores F.
DOB: 08/02/1961""")],
     ["OUT_OF_SCOPE_AGE"], True, [])

case("C37", "On Medicare (SSDI) - out of scope",
     {"name": "Steven G. (synthetic)", "age": 52, "language": "en", "household": "Lives with brother", "notice_received_date": "2026-10-13"},
     [("medicare.txt", """MEDICARE HEALTH INSURANCE
Name: Steven G.
Medicare Number: 1EG4-TE5-MK72 (synthetic)
Entitled to: HOSPITAL (PART A) 01-01-2022   MEDICAL (PART B) 01-01-2022"""),
      ("ssdi.txt", """SOCIAL SECURITY ADMINISTRATION
Notice of Award
Beneficiary: Steven G.
We found that you became disabled under our rules on July 1, 2019.""")],
     ["OUT_OF_SCOPE_MEDICARE", "EX_DISABILITY"], True, [])

case("C38", "Veteran with 100% VA rating",
     {"name": "Marcus H. (synthetic)", "age": 44, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-04"},
     [("va.txt", """DEPARTMENT OF VETERANS AFFAIRS
Benefit Summary Letter
Veteran: Marcus H.
Your combined service-connected evaluation is 100 percent.
You are considered to be totally and permanently disabled due to your service-connected disabilities.""")],
     ["EX_VETERAN_TOTAL"], True, [])

case("C39", "Veteran rated 70% (not total) who volunteers 84 hrs",
     {"name": "Tony R. (synthetic)", "age": 51, "language": "en", "household": "Lives with wife", "notice_received_date": "2026-10-10"},
     [("va.txt", """DEPARTMENT OF VETERANS AFFAIRS
Veteran: Tony R.
Your combined service-connected evaluation is 70 percent."""),
      ("vol.txt", """VFW Post 1234 - Volunteer Hours
Tony R. - September 2026 - 84 hours
Post Commander: Bill Sanders""")],
     ["WORK_80"], True, [])

case("C40", "SNAP household subject to SNAP work rules (ABAWD)",
     {"name": "Shawn K. (synthetic)", "age": 35, "language": "en", "household": "Lives alone", "notice_received_date": "2026-10-17"},
     [("snap.txt", """DEPARTMENT OF TRANSITIONAL ASSISTANCE
SNAP Notice of Approval
Client: Shawn K.
You are an Able-Bodied Adult Without Dependents (ABAWD).
You are subject to SNAP work requirements and must meet them to keep your benefits.""")],
     ["EX_SNAP_TAFDC"], True, [])

case("C41", "SNAP notice says EXEMPT from SNAP work rules (caring for child) + birth cert",
     {"name": "Lena B. (synthetic)", "age": 29, "language": "en", "household": "Self + son (9)", "notice_received_date": "2026-10-03"},
     [("snap.txt", """DEPARTMENT OF TRANSITIONAL ASSISTANCE
SNAP Notice
Client: Lena B.
You are exempt from SNAP work requirements because you are caring for a child under age 14."""),
      ("birth.txt", """BIRTH RECORD - CITY OF LYNN
Child: Noah B.
Date of birth: 04/11/2017
Mother: Lena B.""")],
     ["EX_CAREGIVER_CHILD"], True, [], "SNAP-exempt is not the SNAP exemption; caregiving applies.")

case("C42", "Former foster youth, age 24",
     {"name": "Destiny W. (synthetic)", "age": 24, "language": "en", "household": "Lives with roommate", "notice_received_date": "2026-10-11"},
     [("dcf.txt", """MASSACHUSETTS DEPARTMENT OF CHILDREN AND FAMILIES
Verification of Foster Care
This letter verifies that Destiny W. (DOB 01/30/2002) was in the care and custody of DCF
and in foster care on her 18th birthday, January 30, 2020.""")],
     ["EX_FORMER_FOSTER"], True, [])

case("C43", "Released from county jail in August 2026",
     {"name": "Anthony M. (synthetic)", "age": 31, "language": "en", "household": "Lives with mother", "notice_received_date": "2026-10-06"},
     [("release.txt", """SUFFOLK COUNTY SHERIFF'S DEPARTMENT - HOUSE OF CORRECTION
Certificate of Release
Name: Anthony M.
Date of release: 08/20/2026""")],
     ["EX_INCARCERATION"], True, [])

case("C44", "Tribal member (Mashpee Wampanoag)",
     {"name": "River S. (synthetic)", "age": 40, "language": "en", "household": "Lives with family", "notice_received_date": "2026-10-15"},
     [("tribal.txt", """MASHPEE WAMPANOAG TRIBE - ENROLLMENT OFFICE
Verification of Tribal Enrollment
River S. is an enrolled member of the Mashpee Wampanoag Tribe, a federally recognized tribe.
Enrollment No. MW-0000 (synthetic)""")],
     ["EX_AIAN"], True, [])

case("C45", "Vietnamese speaker in outpatient alcohol treatment program",
     {"name": "Thanh P. (synthetic)", "age": 48, "language": "vi", "household": "Lives with son", "notice_received_date": "2026-09-30"},
     [("program.txt", """DORCHESTER RECOVERY CENTER - Intensive Outpatient Program
Participation Letter
Client: Thanh P.
Thanh P. is currently participating in our alcohol treatment and rehabilitation program
(3 sessions per week) since 08/04/2026.
Clinical Director: Maria Santos, LMHC""")],
     ["EX_SUD_TREATMENT"], True, [])


# ---------------------------------------------------------------- primary demo (illustrative composite, not a real person)
case("C46", "DEMO - Maria: caregiver of her mother after a stroke; doctor letter doesn't state the disability",
     {"name": "Maria L. (illustrative composite)", "age": 34, "language": "es", "city": "Lawrence",
      "household": "Lives with her mother (70), who had a stroke", "notice_received_date": "2026-10-12", "roster_id": "M0001",
      "notes": "Has type 2 diabetes; coverage loss would stop her prescriptions. Renewal letter arrived in English."},
     [("masshealth_rfi_notice.txt", """MASSHEALTH
Request for Information
Notice date: October 9, 2026
To: Maria L.

We need more information to decide if you meet the new work and community engagement requirement,
or if you qualify for an exemption.
Please send us proof within 30 days of receiving this notice.
If you do not send proof, your MassHealth coverage may end."""),
      ("declaracion_cuidadora_foto.txt", """Declaración de cuidadora
Yo, Maria L., vivo con mi madre, Carmen L., en Lawrence.
Desde su derrame cerebral en marzo, la ayudo todos los días a bañarse, vestirse, comer y tomar sus medicinas.
Firma: Maria L.   Fecha: 21/10/2026"""),
      ("carta_neurologia_madre.txt", clinic_letter(
          "Lawrence General Hospital - Neurology Clinic", "Dr. Robert Chen", "MD", "October 20, 2026", "Carmen L.", "05/02/1956",
          """Mrs. L. was hospitalized for an ischemic stroke on March 3, 2026.
She has residual left-sided weakness and is followed in our neurology clinic every 3 months.
Her medications include apixaban and atorvastatin."""))],
     ["EX_CAREGIVER_DISABLED"], False, ["CAREGIVER_DISABILITY_STATEMENT", "DOC_TRANSLATION"],
     "Caregiver exemption applies but the mother's doctor letter names the stroke without stating a disability or daily-care need.")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    # Held-out split: alternate cases, so every scenario family appears in both splits.
    for i, c in enumerate(CASES):
        c["split"] = "dev" if i % 2 == 0 else "test"
        (OUT / f"{c['case_id']}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
    n_test = sum(c["split"] == "test" for c in CASES)
    print(f"wrote {len(CASES)} cases ({len(CASES) - n_test} dev / {n_test} test) to {OUT}")


if __name__ == "__main__":
    main()
