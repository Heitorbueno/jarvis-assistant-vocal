# Financeiro — contas a pagar/receber, bancos e fluxo de caixa

Abra `http://127.0.0.1:8790/panneau` › **Financeiro ↗** (ou direto `/financeiro`).
Tudo fica em `finances/financeiro.db`, no seu PC (pasta não versionada). Nada vai
para o MCP nem para o Hermes. **O Jarvis só registra: não paga nem transfere.**

## Telas
- **Resumo**: saldo nas contas, a pagar atrasado/hoje/7 dias, a receber, saldo
  projetado em 30 dias, gráfico de fluxo de caixa (30–180 dias, com alerta de caixa
  negativo) e próximos vencimentos com botão « Paguei/Recebi ».
- **Lançamentos**: filtros, baixa, estorno, cancelamento, exclusão (só no PC) e
  exportação CSV (abre no Excel).
- **Novo lançamento**: tipo, descrição, valor, vencimento, conta, categoria,
  fornecedor/cliente, recorrência (semanal/mensal/anual) ou parcelas (até 120x).
- **Bancos e contas**: corrente, poupança, cartão, carteira, investimento; saldo
  inicial; conta padrão.
- **Extrato e conciliação**: importe o **OFX** do seu banco (todos os bancos
  brasileiros exportam). Repetidos são ignorados; o Jarvis sugere o título com mesmo
  valor e data ±5 dias e baixa ao conciliar; tarifas etc. entram como « avulso ».
- **Open Finance (Pluggy)**: opcional e pago/trial. Somente leitura de contas e
  transações dos bancos conectados no Pluggy Connect.

## Por voz (pt-BR)
- « Lança conta de luz de 230 reais dia 10 no Itaú » → pede confirmação.
- « Aluguel de 2 mil todo mês dia 5 », « compra de 1.200 em 3 vezes ».
- « O que tenho para pagar essa semana? », « contas atrasadas ».
- « Paguei a conta de luz » → o Jarvis acha o título e pede confirmação para baixar.
- « Como estão minhas finanças? », « vou ficar negativo? ».

Criar, baixar e cancelar são **N2** (confirmação; « sim, sempre » memoriza). Consultar
é N1. Remoto: só com « Cockpit (finanças) remoto » ativado no acesso remoto.
