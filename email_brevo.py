import json
import os
from urllib.request import Request, urlopen

def enviar_email_recuperacao(destinatario, link):
    chave = os.environ.get("BREVO_API_KEY")
    remetente = os.environ.get("BREVO_REMETENTE_EMAIL")
    if not chave or not remetente:
        raise RuntimeError("Brevo nao configurado")
    dados = {
        "sender": {"name": "MOVYLA Training", "email": remetente},
        "to": [{"email": destinatario}],
        "subject": "MOVYLA Training - Recuperacao de senha",
        "htmlContent": (
            "<h2>Recuperacao de senha - MOVYLA Training</h2>"
            "<p>Recebemos uma solicitacao para redefinir sua senha.</p>"
            '<p><a href="' + link + '">Criar uma nova senha</a></p>'
            "<p>Este link expira em 30 minutos e pode ser usado apenas uma vez.</p>"
            "<p>Se voce nao solicitou, ignore este e-mail.</p>"
        )
    }
    requisicao = Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(dados).encode("utf-8"),
        headers={"accept":"application/json","content-type":"application/json","api-key":chave},
        method="POST"
    )
    with urlopen(requisicao, timeout=15) as resposta:
        return resposta.status in (200,201,202)
