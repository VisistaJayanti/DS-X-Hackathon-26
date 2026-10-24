"""Plain-language member explanation templates (offline / fallback translation).

These were machine-drafted and MUST be reviewed by a native speaker before real use.
In live mode, Claude translates the verified English explanation instead.
"""

T = {
    "intro": {
        "en": "Hello {first}. This is a summary from your navigator about your {agency} letter.",
        "es": "Hola, {first}. Este es un resumen de su navegador sobre su carta de {agency}.",
        "pt": "Olá, {first}. Este é um resumo do seu navegador sobre a sua carta do {agency}.",
        "ht": "Bonjou {first}. Sa a se yon rezime navigatè w la fè sou lèt {agency} ou a.",
        "vi": "Xin chào {first}. Đây là bản tóm tắt của người hướng dẫn về thư {agency} của quý vị.",
        "zh": "{first}，您好。这是您的导航员关于您的 {agency} 信件的摘要。",
    },
    "likely": {
        "en": "Based on your documents, you may qualify through: {pathway}.",
        "es": "Según sus documentos, es posible que usted califique por: {pathway}.",
        "pt": "Com base nos seus documentos, você pode se qualificar por: {pathway}.",
        "ht": "Dapre dokiman ou yo, ou ka kalifye pa: {pathway}.",
        "vi": "Dựa trên giấy tờ của quý vị, quý vị có thể đủ điều kiện theo: {pathway}.",
        "zh": "根据您的文件，您可能符合以下条件：{pathway}。",
    },
    "out_of_scope": {
        "en": "Based on your documents, the new work rules may not apply to you: {pathway}.",
        "es": "Según sus documentos, es posible que las nuevas reglas de trabajo no se apliquen a usted: {pathway}.",
        "pt": "Com base nos seus documentos, as novas regras de trabalho podem não se aplicar a você: {pathway}.",
        "ht": "Dapre dokiman ou yo, nouvo règ travay yo ka pa aplike pou ou: {pathway}.",
        "vi": "Dựa trên giấy tờ của quý vị, các quy định mới về việc làm có thể không áp dụng cho quý vị: {pathway}.",
        "zh": "根据您的文件，新的工作要求可能不适用于您：{pathway}。",
    },
    "none": {
        "en": "Right now, your documents do not show a way to meet the requirement or an exemption. Your navigator will go over other options with you.",
        "es": "Por ahora, sus documentos no muestran una forma de cumplir el requisito ni una exención. Su navegador revisará otras opciones con usted.",
        "pt": "Por enquanto, seus documentos não mostram uma forma de cumprir a exigência nem uma isenção. Seu navegador vai rever outras opções com você.",
        "ht": "Kounye a, dokiman ou yo pa montre yon fason pou satisfè egzijans lan oswa yon egzanpsyon. Navigatè w la ap gade lòt opsyon avè w.",
        "vi": "Hiện tại, giấy tờ của quý vị chưa cho thấy cách đáp ứng yêu cầu hoặc được miễn. Người hướng dẫn sẽ xem xét các lựa chọn khác với quý vị.",
        "zh": "目前，您的文件尚未显示您符合要求或可获豁免。您的导航员会和您一起查看其他选择。",
    },
    "ready": {
        "en": "Your documents look complete for this. Your navigator will prepare the response.",
        "es": "Sus documentos parecen completos para esto. Su navegador preparará la respuesta.",
        "pt": "Seus documentos parecem completos para isso. Seu navegador vai preparar a resposta.",
        "ht": "Dokiman ou yo sanble konplè pou sa. Navigatè w la ap prepare repons lan.",
        "vi": "Giấy tờ của quý vị có vẻ đã đầy đủ cho việc này. Người hướng dẫn sẽ chuẩn bị thư trả lời.",
        "zh": "您的文件看起来已经齐全。您的导航员会准备回复。",
    },
    "need_intro": {
        "en": "What is still needed:",
        "es": "Lo que todavía falta:",
        "pt": "O que ainda falta:",
        "ht": "Sa ki toujou manke:",
        "vi": "Những gì vẫn còn cần:",
        "zh": "仍然需要：",
    },
    "deadline": {
        "en": "Please respond by {date}. That is {days} days from today.",
        "es": "Por favor responda antes del {date}. Faltan {days} días.",
        "pt": "Por favor, responda até {date}. Faltam {days} dias.",
        "ht": "Tanpri reponn anvan {date}. Sa fè {days} jou apati jodi a.",
        "vi": "Vui lòng trả lời trước ngày {date}. Còn {days} ngày nữa.",
        "zh": "请在 {date} 之前回复。距今还有 {days} 天。",
    },
    "overdue": {
        "en": "The response date ({date}) has passed. Contact your navigator today.",
        "es": "La fecha para responder ({date}) ya pasó. Comuníquese hoy con su navegador.",
        "pt": "A data para responder ({date}) já passou. Fale hoje com o seu navegador.",
        "ht": "Dat pou reponn lan ({date}) pase deja. Kontakte navigatè w la jodi a.",
        "vi": "Hạn trả lời ({date}) đã qua. Hãy liên hệ người hướng dẫn ngay hôm nay.",
        "zh": "回复日期（{date}）已过。请今天联系您的导航员。",
    },
    "decides": {
        "en": "{agency} makes the final decision. Your navigator will review everything with you before anything is sent.",
        "es": "{agency} toma la decisión final. Su navegador revisará todo con usted antes de enviar cualquier cosa.",
        "pt": "O {agency} toma a decisão final. Seu navegador vai revisar tudo com você antes de enviar qualquer coisa.",
        "ht": "Se {agency} ki pran desizyon final la. Navigatè w la ap revize tout bagay avè w anvan yo voye anyen.",
        "vi": "{agency} là bên đưa ra quyết định cuối cùng. Người hướng dẫn sẽ xem lại mọi thứ với quý vị trước khi gửi.",
        "zh": "最终决定由 {agency} 做出。在发送任何材料之前，您的导航员会和您一起检查所有内容。",
    },
}

T.update({
    "recover_intro": {
        "en": "Your {agency} coverage ended on {term} because paperwork was missing.",
        "es": "Su cobertura de {agency} terminó el {term} porque faltaban papeles.",
    },
    "recover_window": {
        "en": "You may be able to get it back without a new application if you send {submit} by {date}. That is {days} days from today.",
        "es": "Es posible que pueda recuperarla sin una nueva solicitud si envía {submit} antes del {date}. Faltan {days} días.",
    },
    "recover_no_promise": {
        "en": "This is not a promise: {agency} reviews what you send and decides.",
        "es": "Esto no es una promesa: {agency} revisa lo que usted envíe y decide.",
    },
    "recover_expired": {
        "en": "The time to get coverage back without a new application ended on {date}. You can still apply again, and your navigator can help today.",
        "es": "El plazo para recuperar la cobertura sin una nueva solicitud terminó el {date}. Todavía puede volver a solicitarla y su navegador le puede ayudar hoy.",
    },
    "transition_intro": {
        "en": "Based on your documents and what you told us, you may no longer qualify for {agency} because {trigger}. {agency} makes the final decision.",
        "es": "Según sus documentos y lo que nos dijo, es posible que ya no califique para {agency} porque {trigger}. {agency} toma la decisión final.",
    },
    "transition_options": {
        "en": "So you are not left without coverage, here are options to look at. You choose:",
        "es": "Para que no se quede sin cobertura, estas son opciones que puede considerar. Usted decide:",
    },
    "transition_deadline": {
        "en": "To avoid a gap, try to enroll before {avoid}. The window to enroll closes on {closes}.",
        "es": "Para no quedarse sin cobertura, trate de inscribirse antes del {avoid}. El plazo para inscribirse termina el {closes}.",
    },
    "transition_docs": {
        "en": "Papers to have ready: {docs}.",
        "es": "Papeles que debe tener listos: {docs}.",
    },
    "transition_wrong": {
        "en": "If anything here is wrong, tell your navigator. Your navigator will help you with the next step.",
        "es": "Si algo aquí no es correcto, dígaselo a su navegador. Su navegador le ayudará con el siguiente paso.",
    },
})


def pathway_name(pid, lang):
    from . import rulebook
    names = rulebook.pathway(pid)["member_name"]
    return names.get(lang, names["en"])


def gap_text(code, lang):
    from . import rulebook
    texts = rulebook.gap(code)["member_text"]
    return texts.get(lang, texts["en"])


def t(key, lang, **kw):
    from . import rulebook
    kw.setdefault("agency", rulebook.program()["agency"])
    return T[key].get(lang, T[key]["en"]).format(**kw)
