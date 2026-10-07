FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LLM_MODE=auto

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY shared/ shared/
COPY a1_loan_lifecycle/ a1_loan_lifecycle/
COPY a2_chem_demand/ a2_chem_demand/
COPY evals/ evals/

RUN useradd --create-home appuser && mkdir -p runtime && chown -R appuser /app
USER appuser

EXPOSE 8501 8502
# APP selects which prototype to serve: a1_loan_lifecycle | a2_chem_demand
ENV APP=a1_loan_lifecycle PORT=8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://localhost:{os.environ[\"PORT\"]}/_stcore/health')"
CMD ["sh", "-c", "streamlit run $APP/app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false"]
