"""Guided intake questions.

Closed answers are stored as language-independent codes, so the clinician view
is the same whatever language the patient used. Free-text answers are stored
exactly as typed, tagged with their language, and are NOT machine-translated.

Hindi and Telugu wording is a first draft and must be validated by qualified
native speakers (and a clinician) before any use with real patients.
"""

LANGS = {"en": "English", "hi": "हिंदी (Hindi)", "te": "తెలుగు (Telugu)"}

QUESTIONS = [
    {"id": "chief_complaint", "kind": "complaint", "label": "Main complaint", "type": "text",
     "text": {"en": "What is the main problem you have come for today?",
              "hi": "आज आप किस मुख्य समस्या के लिए आए हैं?",
              "te": "ఈ రోజు మీరు ఏ ముఖ్య సమస్య కోసం వచ్చారు?"}},
    {"id": "duration", "kind": "complaint", "label": "Duration of complaint", "type": "single",
     "text": {"en": "How long have you had this problem?",
              "hi": "यह समस्या कितने समय से है?",
              "te": "ఈ సమస్య ఎంత కాలంగా ఉంది?"},
     "options": {
         "lt_1w": {"en": "Less than 1 week", "hi": "1 सप्ताह से कम", "te": "1 వారం కంటే తక్కువ"},
         "1_4w": {"en": "1-4 weeks", "hi": "1-4 सप्ताह", "te": "1-4 వారాలు"},
         "1_6m": {"en": "1-6 months", "hi": "1-6 महीने", "te": "1-6 నెలలు"},
         "gt_6m": {"en": "More than 6 months", "hi": "6 महीने से अधिक", "te": "6 నెలల కంటే ఎక్కువ"}}},
    {"id": "known_conditions", "kind": "history", "label": "Previously diagnosed conditions",
     "type": "multi",
     "text": {"en": "Has a doctor ever told you that you have any of these?",
              "hi": "क्या किसी डॉक्टर ने कभी बताया है कि आपको इनमें से कोई समस्या है?",
              "te": "ఈ సమస్యల్లో ఏదైనా మీకు ఉందని డాక్టర్ ఎప్పుడైనా చెప్పారా?"},
     "options": {
         "diabetes": {"en": "Diabetes (sugar)", "hi": "मधुमेह (शुगर)", "te": "మధుమేహం (షుగర్)"},
         "hypertension": {"en": "High blood pressure", "hi": "उच्च रक्तचाप (बीपी)", "te": "అధిక రక్తపోటు (బీపీ)"},
         "thyroid": {"en": "Thyroid problem", "hi": "थायरॉइड समस्या", "te": "థైరాయిడ్ సమస్య"},
         "asthma": {"en": "Asthma", "hi": "दमा (अस्थमा)", "te": "ఆస్తమా"},
         "kidney": {"en": "Kidney disease", "hi": "किडनी की बीमारी", "te": "కిడ్నీ వ్యాధి"},
         "none": {"en": "None of these", "hi": "इनमें से कोई नहीं", "te": "ఏదీ లేదు"}}},
    {"id": "current_medicines", "kind": "medication", "label": "Current medicines", "type": "text",
     "text": {"en": "Which medicines are you taking now? (write the names, or 'none')",
              "hi": "आप अभी कौन-सी दवाइयाँ ले रहे हैं? (नाम लिखें, या 'कोई नहीं')",
              "te": "మీరు ఇప్పుడు ఏ మందులు వాడుతున్నారు? (పేర్లు రాయండి, లేదా 'ఏమీ లేవు')"}},
    {"id": "allergy", "kind": "allergy", "label": "Allergy to medicine or food", "type": "single",
     "text": {"en": "Are you allergic to any medicine or food?",
              "hi": "क्या आपको किसी दवा या भोजन से एलर्जी है?",
              "te": "మీకు ఏదైనా మందు లేదా ఆహారం వల్ల అలర్జీ ఉందా?"},
     "options": {"yes": {"en": "Yes", "hi": "हाँ", "te": "అవును"},
                 "no": {"en": "No", "hi": "नहीं", "te": "లేదు"},
                 "unsure": {"en": "Not sure", "hi": "पता नहीं", "te": "తెలియదు"}}},
    {"id": "allergy_detail", "kind": "allergy", "label": "Allergy details", "type": "text",
     "text": {"en": "If yes, to what?", "hi": "अगर हाँ, तो किससे?", "te": "అవును అయితే, దేనికి?"}},
]


def build_answers(raw: dict, lang: str) -> list[dict]:
    """Turn form values into record-ready answers (codes + English labels)."""
    out = []
    for q in QUESTIONS:
        v = raw.get(q["id"])
        if q["type"] == "text":
            v = (v or "").strip()
            out.append({"question_id": q["id"], "kind": q["kind"], "label": q["label"],
                        "value": v, "answer_text": v})
        elif q["type"] == "single":
            out.append({"question_id": q["id"], "kind": q["kind"], "label": q["label"],
                        "value": q["options"][v]["en"] if v else None,
                        "answer_text": q["options"][v][lang] if v else None})
        else:
            v = v or []
            out.append({"question_id": q["id"], "kind": q["kind"], "label": q["label"],
                        "value": [q["options"][o]["en"] for o in v],
                        "answer_text": ", ".join(q["options"][o][lang] for o in v)})
    return out
