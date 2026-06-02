# OWASP ZAP Baseline

O ZAP baseline não foi executado neste sandbox porque Docker/serviço persistente externo não está disponível aqui.

Comando recomendado em staging:

```bash
docker run --rm -t owasp/zap2docker-stable zap-baseline.py -t https://valora-finance.onrender.com -r zap_report.html
```

Executar apenas baseline passivo/seguro no domínio próprio.
