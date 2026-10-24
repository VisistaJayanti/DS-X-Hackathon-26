"""Outreach stage: pick channels for a flagged member and write the messages in their language.

initial()  - before documents: help the member recognise and answer the notice, offer help, deadline.
followup() - after the gap stage: exactly what to send / collect (SMS photo request, CHW checklist).
Every message tells the member how to contact the agency directly (no dark patterns), never asks for
sensitive identifiers by text, and never claims a decision. TV/radio is population-level and out of scope.
"""
from .. import config, i18n, rulebook
from ..llm import LLMUnavailable, call_json

T = {
    "sms": {
        "en": "Hi {first}, this is your health plan's care team. Your {agency} letter about keeping your coverage needs an answer by {due}. "
              "We can help for free - reply YES and we'll call you. You can also call {contact}. Reply STOP to opt out.",
        "es": "Hola {first}, le escribe el equipo de atención de su plan de salud. Su carta de {agency} sobre mantener su cobertura necesita "
              "respuesta antes del {due}. Le ayudamos gratis: responda SÍ y le llamamos. También puede llamar a {contact}. Responda STOP para no recibir más mensajes.",
        "pt": "Olá {first}, aqui é a equipe de cuidado do seu plano de saúde. Sua carta do {agency} sobre manter sua cobertura precisa de resposta "
              "até {due}. Ajudamos de graça: responda SIM e ligamos para você. Você também pode ligar para {contact}. Responda STOP para sair.",
        "ht": "Bonjou {first}, se ekip swen plan sante w la. Lèt {agency} ou a sou kenbe asirans ou bezwen yon repons anvan {due}. "
              "Nou ka ede w gratis: reponn WI epi n ap rele w. Ou ka rele {contact} tou. Reponn STOP pou w pa resevwa plis mesaj.",
        "vi": "Chào {first}, đây là nhóm chăm sóc của chương trình bảo hiểm sức khỏe. Thư {agency} về việc giữ bảo hiểm cần được trả lời trước {due}. "
              "Chúng tôi giúp miễn phí - trả lời CÓ để chúng tôi gọi. Quý vị cũng có thể gọi {contact}. Trả lời STOP để ngừng nhận tin.",
        "zh": "{first}您好，这里是您健康计划的护理团队。您关于保留保险的 {agency} 信件需要在 {due} 前回复。我们可免费帮助您——回复“是”，我们会给您打电话。"
              "您也可以拨打 {contact}。回复 STOP 退订。",
    },
    "sms_photo": {
        "en": "Thanks {first}! To finish your {agency} paperwork, please send a photo of: {items}. Please don't text your Social Security number.",
        "es": "¡Gracias, {first}! Para terminar sus papeles de {agency}, envíe una foto de: {items}. Por favor no envíe su número de Seguro Social por mensaje.",
        "pt": "Obrigado, {first}! Para terminar seus papéis do {agency}, envie uma foto de: {items}. Por favor, não envie seu número do Seguro Social por mensagem.",
        "ht": "Mèsi {first}! Pou nou fini papye {agency} ou yo, tanpri voye yon foto: {items}. Tanpri pa voye nimewo Sekirite Sosyal ou pa tèks.",
        "vi": "Cảm ơn {first}! Để hoàn tất giấy tờ {agency}, vui lòng gửi ảnh của: {items}. Vui lòng không nhắn số An sinh Xã hội.",
        "zh": "谢谢您，{first}！为完成您的 {agency} 材料，请发送以下文件的照片：{items}。请不要通过短信发送您的社会安全号码。",
    },
    "phone": {
        "en": ["Hello, may I speak with {first}? I'm calling from your health plan's care team about your {agency} letter. Is now a good time?",
               "{agency} sent you a letter called \"{notice}\". It needs an answer by {due}, or your coverage could end - even if you still qualify.",
               "Many people don't have to meet the new rules. Can I ask a few questions? Do you care for a child 13 or younger, or an adult "
               "with a disability? Do you have a health condition that makes it hard to work? Do you work, volunteer, or go to school?",
               "We can help you collect the papers and fill everything out, for free. I will never ask for your Social Security number on this call.",
               "You can always call {agency} directly at {contact}. {agency} makes the final decision."],
        "es": ["Hola, ¿puedo hablar con {first}? Le llamo del equipo de atención de su plan de salud por su carta de {agency}. ¿Es buen momento?",
               "{agency} le envió una carta llamada \"{notice}\". Necesita respuesta antes del {due}, o su cobertura podría terminar, aunque usted todavía califique.",
               "Muchas personas no tienen que cumplir las nuevas reglas. ¿Le puedo hacer unas preguntas? ¿Cuida a un niño de 13 años o menos, o a un adulto "
               "con discapacidad? ¿Tiene una condición de salud que le dificulta trabajar? ¿Trabaja, hace voluntariado o estudia?",
               "Le podemos ayudar a reunir los papeles y llenar todo, gratis. Nunca le pediré su número de Seguro Social en esta llamada.",
               "Siempre puede llamar directamente a {agency} al {contact}. {agency} toma la decisión final."],
    },
    "mail": {
        "en": ["Look for your {agency} letter. {conventions}",
               "It is called \"{notice}\". Answer it by {due}.",
               "Need help? Call your health plan's care team, or call {agency} directly at {contact}."],
        "es": ["Busque su carta de {agency}. {conventions}",
               "Se llama \"{notice}\" (está en inglés). Respóndala antes del {due}.",
               "¿Necesita ayuda? Llame al equipo de atención de su plan de salud, o llame directamente a {agency} al {contact}."],
    },
    "chw_intro": {
        "en": "Home visit checklist for {first} (bring a document scanner app; the member keeps all originals):",
        "es": "Lista para la visita a domicilio de {first} (lleve una aplicación de escáner; el miembro se queda con todos los originales):",
    },
}


def _t(key, lang, **kw):
    v = T[key].get(lang)
    fallback = v is None
    v = v if v is not None else T[key]["en"]
    if isinstance(v, list):
        return [s.format(**kw) for s in v], fallback
    return v.format(**kw), fallback


def choose_channels(m):
    ch = []
    if m.get("sms_opt_in"):
        ch.append(("sms", "Opted in to text messages"))
    if m.get("has_mobile", True) or m.get("preferred_channel") == "phone":
        ch.append(("phone", "Phone on file" + (" (preferred)" if m.get("preferred_channel") == "phone" else "")))
    if not m.get("returned_mail") and not m.get("address_change_90d"):
        ch.append(("mail", "Mailing address is current"))
    if m.get("returned_mail") or m.get("missed_prior_notices", 0) >= 2 or not m.get("has_mobile", True) or m.get("preferred_channel") == "in_person":
        ch.append(("chw_visit", "Hard to reach by mail/phone: community health worker visit"))
    if not ch:
        ch.append(("chw_visit", "No reliable remote channel"))
    return ch


def _kw(member, deadline):
    prog = rulebook.program()
    contact = prog["contact_line"]
    if isinstance(contact, dict):
        contact = contact.get(member.get("language", "en"), contact["en"])
    return {"first": member["name"].split()[0], "agency": prog["agency"], "due": deadline["due"] if deadline else "the date on the letter",
            "contact": contact, "notice": prog["notice_name"], "conventions": " ".join(prog.get("notice_conventions", []))}


TR_SYSTEM = """Translate this health-plan outreach message into {lang}. Warm, plain, 6th-grade level. Keep dates, numbers,
names and the agency name exactly. Do not add, remove or soften anything (keep the opt-out and the direct-contact line)."""
TR_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "string"}}}, "required": ["lines"],
             "additionalProperties": False}


def _localize(lines, lang, fallback, meter, use_llm):
    if not fallback or lang == "en":
        return lines, "template"
    if use_llm:
        try:
            data, _ = call_json("translate", TR_SYSTEM.format(lang=config.LANGUAGES.get(lang, lang)), "\n".join(lines), TR_SCHEMA,
                                max_tokens=4000, meter=meter)
            if len(data["lines"]) == len(lines):
                return data["lines"], "llm"
        except LLMUnavailable:
            pass
    return lines, "english_fallback"


def initial(member, deadline, meter, use_llm=True):
    lang = member.get("language", "en")
    kw = _kw(member, deadline)
    msgs = []
    for ch, why in choose_channels(member):
        if ch == "sms":
            text, fb = _t("sms", lang, **kw)
            lines, eng = _localize([text], lang, fb, meter, use_llm)
        elif ch == "phone":
            lines, fb = _t("phone", lang, **kw)
            lines, eng = _localize(lines, lang, fb, meter, use_llm)
        elif ch == "mail":
            lines, fb = _t("mail", lang, **kw)
            lines, eng = _localize(lines, lang, fb, meter, use_llm)
        else:
            text, fb = _t("chw_intro", lang, **kw)
            lines, eng = _localize([text, "• " + kw["notice"] + f" ({kw['agency']})", "• Photo ID"], lang, True, meter, use_llm) \
                if fb else ([text, f"• {kw['notice']} ({kw['agency']})", "• ID"], "template")
        msgs.append({"channel": ch, "why": why, "language": lang, "lines": lines, "engine": eng})
    return {"channels": [c for c, _ in choose_channels(member)], "messages": msgs,
            "out_of_scope": "TV/radio awareness campaigns are population-level and not generated per member."}


def followup(member, gaps_out, meter, use_llm=True):
    lang = member.get("language", "en")
    kw = _kw(member, gaps_out.get("deadline"))
    items = [g for g in gaps_out["gaps"] if g["ask"] in ("member", "clinician", "school", "employer")]
    if not items:
        return {"messages": [], "note": "Nothing further needed from the member."}
    names = [i18n.gap_text(g["code"], lang).rstrip(".") for g in items]
    msgs = []
    if member.get("sms_opt_in"):
        text, fb = _t("sms_photo", lang, items="; ".join(n[0].lower() + n[1:] for n in names), **kw)
        lines, eng = _localize([text], lang, fb, meter, use_llm)
        msgs.append({"channel": "sms", "why": "Ask for a photo of the missing document", "language": lang, "lines": lines, "engine": eng})
    head, _ = _t("chw_intro", lang, **kw)
    checklist = [head] + [f"• {i18n.gap_text(g['code'], lang)}" for g in items] + \
                [f"• [{g['ask']}] {g['fix']}" for g in items if g["ask"] != "member"] + [f"• {kw['notice']} ({kw['agency']})"]
    msgs.append({"channel": "chw_visit", "why": "Exactly what to collect", "language": lang, "lines": checklist, "engine": "template"})
    return {"messages": msgs}
