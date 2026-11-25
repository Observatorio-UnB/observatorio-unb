# Imagem única do pipeline e do painel (ver docker-compose.yml).
FROM python:3.12-slim

# PYTHONPATH=/app: o painel roda com `streamlit run src/dashboard/app.py`, e o Streamlit só põe no
# path a pasta do script. Sem a raiz, `from src.db ...` falha em silêncio, o painel não chega ao
# banco e, como export/ não entra na imagem (.dockerignore), abre sem dados.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt requirements-dbt.txt ./
RUN pip install -r requirements.txt -r requirements-dbt.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "src/dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
