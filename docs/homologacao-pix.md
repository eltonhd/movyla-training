# MOVYLA — homologação segura do Pix

Este roteiro é para **ambiente separado de homologação**. Não configure as variáveis de teste no serviço de produção do Render.

## Pré-requisitos
- Criar um serviço de homologação separado, com banco de dados e armazenamento independentes.
- Publicar apenas a branch `desenvolvimento-seguro-20261013` nesse serviço, após revisão.
- Usar credenciais de teste do Mercado Pago armazenadas exclusivamente nas variáveis secretas do ambiente; **nunca** enviar tokens por chat, logs ou GitHub.
- Validar com a documentação atual da API de Orders os campos de resposta, o formato do identificador e a assinatura das notificações. Os testes unitários usam respostas simuladas.
- Conferir que o endereço público do webhook aponta somente para homologação.

## Variáveis previstas
| Variável | Uso |
|---|---|
| `MERCADO_PAGO_ACCESS_TOKEN` | Token da conta de teste; segredo |
| `MERCADO_PAGO_WEBHOOK_SECRET` | Segredo de assinatura do webhook; segredo |
| `MOVYLA_PIX_TESTE_HABILITADO` | `1` habilita a rota de geração Pix |
| `MOVYLA_WEBHOOK_TESTE_HABILITADO` | `1` habilita recebimento do webhook |
| `MOVYLA_RENOVACAO_PIX_TESTE_HABILITADA` | `1` permite liquidação/renovação; deixar **desligada** inicialmente |

## Sequência de validação
1. Manter **todas as flags desligadas**; verificar login e isolamento de contas no ambiente de homologação.
2. Validar a criação de uma cobrança de teste e o QR Code, sem realizar pagamento real.
3. Reabrir a cobrança e confirmar que a mesma Order e o mesmo QR são recuperados.
4. Ativar apenas o webhook de homologação; verificar assinatura válida, rejeição de assinatura inválida e consulta autenticada da Order. A renovação continua desligada.
5. Somente depois de validar respostas reais do provedor e segurança do ambiente, considerar habilitar a segunda flag em homologação.
6. Confirmar pagamento aprovado, valor, moeda, referência, tipo Pix e vínculo com cobrança; repetir a notificação e verificar que o vencimento muda apenas uma vez.
7. Testar falha de banco, status pendente, valor divergente, webhook duplicado e concorrência. Revisar logs sem segredos.
8. **Não migrar para produção automaticamente.** Exigir revisão e autorização explícita.

## Estado atual
A suíte de GitHub Actions usa mocks: aprovação dos testes **não equivale** a transação real homologada no Mercado Pago. A integração de pagamentos reais não foi validada. Não ativar renovação em produção.
